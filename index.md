# Basketball Shot Tracker
ShotSync is a wireless basketball analytics system consisting of a wrist-mounted motion sensor (IMU) and a hoop-mounted outcome detector. It pairs wrist mechanics with shot results to report important measurements like peak wrist speed, snap duration, follow-through, and shooting percentage. It also determines how consistent someones shot is, a important feature to facilitate improvement. The goal is to give athletes objective data they can use to study the consistency of their shooting motion, and identify areas of improvement. 

| Lochlan McCarroll | Los Altos High School | Electrical Engineering | Incoming Freshman |
  
# Final Milestone – Wireless Integration and Analytics Dashboard

<iframe width="1018" height="572" src="https://www.youtube.com/embed/Jd8b29AiIYE" title="Lochlan M. Demo Night Presentation" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>

For the final milestone, I integrated the wrist and hoop modules together into one system. Milestones 1 and 2 established the two separate sensing systems: the hoop module classified the result of the shot, while the wrist module detected likely releases and measured wrist motion. The goal of Milestone 3 was to connect these modules, pair their detections, and calculate useful shooting metrics displayed through an athlete dashboard. 

Miniaturizing the Wrist Module:

The first major task was transferring the wrist system from the larger Arduino Nano ESP32 and external LSM6DS3 IMU used during development to a Seeed Studio XIAO nRF52840 Sense.
The XIAO was much better suited for a wearable device because it was a smaller physical board, had an onboard LSM6DS3TR-C, supported Bluetooth Low Energy (BLE), Battery-power support, and
enough processing power to record and filter motion data. Because the IMU was built directly into the XIAO, I no longer needed a separate sensor board or several loose jumper wires - a critical hardware development for a device meant for athletic motions. The wrist IMU samples motion at approximately 104 times per second, or once every 9.6 milliseconds. The system continuously stores recent samples in a circular pre-release buffer. A circular release buffer was used because the XIAO is always saving the newest sensor readings in a fixed-size memory area. When that area fills, new readings replace the oldest ones. Therefore, when a release is detected, the program has measurements from immediately before detection. When the gyroscope pattern matched the release-candidate conditions (wrist moving in a shot-like motion), the program saved approximately half a second of motion from before the trigger and half a second after it. This created a motion window containing all motion prior to the release instead of only measuring the instant when a threshold was crossed.

<img width="425" height="428" alt="image" src="https://github.com/user-attachments/assets/92bfd1fc-b436-4aa6-9a3f-047fbb0ca130" />
*Diagram of a Circular Pre-Release Buffer

Adding Bluetooth to Both Modules:

I next added Bluetooth Low Energy communication to both the wrist and hoop modules. In the final Bluetooth architecture, the XIAO and Nano ESP32 acted as Bluetooth peripheral devices. 
The computer acted as the Bluetooth central device. A Python program used the Bleak library to search for both modules, connect to them, subscribe to their data characteristics (meaning look for data if they send it), and automatically attempt to reconnect if either device disconnected. For the hoop module, it only needed to send one small event packet after classifying a result. That packet included information such as:

* Hoop event number
* Microcontroller timestamp
* Shot result
* Whether rim contact occurred
* Piezoelectric peak
* Infrared beam-break duration

The result was then encoded as one of three categories based on the metrics above:

* CLEAN_MAKE
* MAKE_WITH_RIM_CONTACT
* RIM_MISS

Solving Wrist Data Transmission:

Bluetooth communication was more difficult for the wrist module because each shot contained an entire sequence of sensor readings rather than one result. My first approach converted every wrist sample into a long line of text containing the timestamp with acceleration and gyroscope values. However, Bluetooth Low Energy commonly transfers small pieces of data at a time. Each text line had to be divided into multiple transmissions, producing a large amount of Bluetooth traffic. Some pieces arrived late or failed to arrive, which meant that reconstructed shots occasionally contained missing samples. Consequently, if someone was to shoot multiple shots in a row without waiting, the system would miss them because it would transmitting. 

To fix this, I sent the data using binary packets. Each transmitted wrist sample became one fixed 20-byte packet containing:
* A packet marker
* A protocol version
* Shot identification number
* Sample index
* Time relative to the detected release
* Three acceleration measurements
* Three gyroscope measurements

A binary packet works by storing numbers directly as bytes instead of converting them to written characters. For example, to send the number 150 as text, the XIAO must look up the text characters for "1", "5", and "0". Each character requires 1 byte of data resulting in a total size transmitted of 3 bytes (and if you add a comma or space, it becomes 4). In binary, the number 150 is just a value. This means it can send more data faster because transmitted data takes up less memory space. Also, when sending everything as text, it causes the message to be "cut up". If a string of text that holds all the data is over 20 bytes (the limit for BLE), it gets split and the program has to "glue" it back together once transmitted. 

Each packet also contained a shot number and sample index. This made sure the Python Program (that receives the data) could accurately pair the wrist and hoop bluetooth transmissions and place samples in the correct shot. This accomplished other functions: restoring their correct order, ignore duplicate packets, detect missing packets, donfirm when a complete motion window had arrived, and pairing Wrist and Hoop Events.

After both Bluetooth connections worked, the next step was a Python integration program that combined the two independent event streams. The wrist and hoop did not share the same internal clock. Each microcontroller started its timer when it powered on, so their raw timestamps could not be compared directly. Instead, the Python program recorded the computer’s monotonic arrival time whenever it received an event. A monotonic clock measures elapsed time and cannot move backward if the computer’s displayed clock changes (a glorified stopwatch). This made it more appropriate for matching sensor events than a normal date-and-time clock. When the wrist detected a release candidate, Python stored it in a queue of pending wrist events. When the hoop reported a result, Python stored that event in a queue of pending hoop events. The program searched for the most recent valid wrist candidate that occurred within the allowed timing window around the hoop event. The pairing window allowed the hoop event to arrive slightly before the wrist event because Bluetooth messages could be delayed or processed in a different order. A hoop event could be paired with a wrist candidate from 0.20 seconds later to 2.75 seconds earlier. Events that were not paired within approximately 3.5 seconds expired so they could not accidentally match a later shot.

Once a valid pair was found, the program took one wrist release candidate, one complete wrist-motion sample window, and one hoop result. The program only showed a completed shot had occurred after it possessed both the paired hoop result and the finished wrist analytics. This prevented incomplete shots from appearing on the dashboard. This architecture also handled false wrist triggers. A pass or unusual wrist movement could occasionally create a release candidate, but it would not become a completed shot unless a corresponding hoop event occurred.

Calculating Wrist Analytics:

After receiving the complete sample window, Python calculated several wrist-motion metrics like the following. 

Peak Wrist Speed

For every sample, the program combined the three gyroscope axes to calculate total angular speed. The largest value in the window (what axis rotating the most) became the peak wrist speed, measured in degrees per second. This represented the fastest rotational moment captured during the release.

Motion Onset

To estimate when the main shooting movement began, the program examined the samples before the main gyroscope peak. It searched backward for a short sequence of relatively quiet samples (dormant wrist movement), then treated the samples after as the beginning of the release movement. The quiet-motion threshold adjusted according to the baseline noise in that particular shot window, a more reliable than using one fixed threshold for every motion.

Snap Duration

Snap duration measured how long the main wrist-speed peak remained above 40% of its maximum value. The program began at the peak, searched backward until angular speed fell below 40% of the peak, and then searched forward until it fell below that level again. The time between those boundaries became the snap duration. This metric described how long the main wrist-speed peak was, not simply whether the wrist moved quickly.

Follow-Through

Follow-through was estimated as the time between the release trigger and the point when the wrist returned to relatively low motion. To avoid treating a single low reading as the end of the movement, the program required five consecutive low-motion samples. This helped distinguish genuine settling from a brief fluctuation in the sensor data.

Estimated Wrist Rotation

The gyroscope measured angular velocity rather than angle directly. To estimate how far the wrist rotated, Python used integration for each gyroscope axis over time. 
Integration finds the area under an angular-velocity-versus-time graph. Since angular velocity was measured in degrees per second, integrating it over seconds produced an estimated rotation in degrees. The program used trapezoidal integration, which approximated the area between each pair of measurements as a trapezoid. The system calculated estimated rotation around the X, Y, and Z axes. 

Release Acceleration

The system combined the three accelerometer axes to calculate total acceleration. It recorded both the acceleration at the estimated release marker and the largest acceleration observed anywhere in the motion window. The displayed acceleration included gravity, so it represented the total acceleration measured by the device rather than only acceleration created by the athlete.

Athlete Profiles and Personal Baselines:

I added athlete accounts so that multiple players could use the same hardware without combining their data. Before shooting, the user must select an athlete on the dashboard. When the wrist detects a release, Python records the currently selected athlete and assigns the completed shot to that account. This combined all shots belonging to one athlete into a continuing history. Each athlete developed a personal baseline (see below) from their previous shot. This was important because ShotSync was not intended to claim that every basketball player should have the same wrist speed, snap duration, or rotation. Different athletes can shoot in different ways and still be successful. 

Form Match Score:

The dashboard generated a Form Match score after the athlete had at least five previous shots. The baseline could include up to the 15 most recent prior shots. The score compared these. six metrics: Peak wrist speed, Snap duration, Time from motion onset to release, Follow-through duration, Primary-axis rotation, Secondary-axis rotation. For each metric, the program calculated how much the current shot was different from the athlete’s baseline average. It then divided that difference by a scale based on the baseline’s normal variation. This normalization was important. A difference of 20 milliseconds might be significant for one metric but insignificant for another. Dividing by each metric’s normal spread allowed the different measurements to contribute more fairly to the combined score, making sure drastic outliers in the data wouldn't skew results. Minimum scale values were also used so that a baseline with almost no numerical variation would not make a tiny difference appear extremely important. The normalized differences were averaged and converted into a score from 0 to 100. 
A high Form Match therefore meant that the shot’s wrist mechanics were similar to the athlete’s recent baseline, the player would shoot the ball the same way every time. It did not mean that the release was universally correct, nor did it guarantee that the shot would go in. All in all, Form Match measured mechanical consistency, not perfect technique. This is actually crucial for someones shot because an inconsistent pattern is a clear sign a player has a mistake in there form, like a thumb flick (shooting the ball with assistance from your off hand), an incomplete follow through (stopping your shot too early), or hitching/pausing on the way up (bring the ball over your head or pausing before shooting). All of these prevent basketball players from great shooting percentages.


Building the Web Dashboard:

I developed the final website using Streamlit and Plotly. Images of the website are the 4 pictures below.

The dashboard displayed:
- Wrist and hoop connection status
- Current athlete
- Current workout statistics
- Makes, misses, and shooting percentage
- Current streak
- Latest shot result
- Form Match
- Peak wrist speed
- Snap duration
- Follow-through
- Primary wrist rotation
- Release acceleration
- Raw wrist-motion graphs
- Athlete history
- Make-versus-miss comparisons

<img width="1187" height="781" alt="Screenshot 2026-07-31 at 3 34 33 PM" src="https://github.com/user-attachments/assets/b647ea39-02b9-4eed-b0ff-6493eea8cb56" />
*Image of main dashboard page

<img width="1178" height="812" alt="Screenshot 2026-07-31 at 3 31 48 PM" src="https://github.com/user-attachments/assets/6331d76a-1e3c-4894-a27e-2957aaf6009a" />
*Image of the main analytics page 

<img width="1181" height="448" alt="Screenshot 2026-07-31 at 3 33 14 PM" src="https://github.com/user-attachments/assets/896f3463-5f79-4bb1-b294-2cc5fa4cf40d" />
*Image of Deeper analytics (Form Match Score Graph)

<img width="1213" height="797" alt="Screenshot 2026-07-31 at 3 32 09 PM" src="https://github.com/user-attachments/assets/8c55136a-1579-4240-b7b4-5b34fe5d0412" />
*Image of Wrist speed graph and Data 

<img width="1206" height="278" alt="Screenshot 2026-07-31 at 3 33 21 PM" src="https://github.com/user-attachments/assets/0869dbaf-b5e9-4ffb-863f-9f4d8a7e25ec" />
*Table showing what values differ for specific shot outcomes

Milestone 3 Outcome:

By the completion of Milestone 3, ShotSync operated as a complete wireless basketball analytics system. The final system could detect likely releases from a wrist-mounted IMU and capture the motion before and after the release, calculating wrist-speed, timing, acceleration, and rotation metrics. The hoop could classify clean makes, rim-contact makes, and rim misses. Both devices transmit data from both modules over Bluetooth. Python prgrams pair wrist and hoop events, reject unconfirmed wrist movements, and save summary and raw data. The web dashboard then maintains separate athlete profiles, build personal shooting baselines, and displays results through a live web dashboard. 

Future Improvements:

The next step would be validating ShotSync with a larger and more diverse dataset. I primarily developed the release detector and analytics using a limited number of athletes (my instructors and peers). Testing with more players would show which thresholds should be very personalized to a person and which measurements remain useful across different shooting forms. I would also like to test the system more extensively on a regulation hoop and redesign the hoop sensors into a quicker clip-on mounting system. Custom 3D-printed enclosures could protect the electronics, hold the sensors in repeatable positions, and improve the appearance of both modules. And with enough labeled data, I could investigate which wrist measurements correlate with high shooting percentage for individual athletes. Eventually, ShotSync could predict if you make or miss a shot based on your form and mechanics. Because it knows so much about your shot and what numbers change when you miss, a future version could also connect meaningful baseline deviations with coach-reviewed training recommendations. For example, the dashboard might recognize that an athlete’s snap duration or primary rotation was unusually different and suggest a relevant form-shooting drill or instructional video. 


# Second Milestone - Wrist IMU and Release Detection

<iframe width="1018" height="572" src="https://www.youtube.com/embed/IMOSZjr0L8E" title="Lochlan M. Milestone 2" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>

For my second milestone, I designed and built the wrist-sensing module for my basketball shot analytics system. The purpose of this module was to measure the motion of the shooter’s wrist during a release and collect data that could later be compared with the result detected by the hoop module from Milestone 1. The wrist module used an LSM6DS3 inertial measurement unit (IMU) mounted securely to the middle of the back of the shooting wrist, along with an Arduino Nano ESP32 as the temporary development board. 

<img width="275" height="663" alt="Screenshot 2026-07-31 at 4 08 46 PM" src="https://github.com/user-attachments/assets/4ac563b4-bd21-4996-bd4e-be133ef76f6e" />
*Prototype of the NanoESP32 and IMU system

Detecting a Release:

The IMU measured three-axis linear acceleration and three-axis angular velocity at approximately 104 samples per second. Sampling at approximately 104 Hz meant that the IMU collected a new measurement roughly every 9.6 milliseconds. This was fast enough to capture the short wrist-snap motion and observe how angular velocity changed before, during, and after release. I programmed the system to record the X, Y, and Z acceleration values, total acceleration, X, Y, and Z gyroscope values, total angular velocity, and timestamps. These axis directions depended on the physical orientation of the IMU. I therefore mounted the sensor consistently on the back of the right wrist so that the same shooting motion would produce comparable X-, Y-, and Z-axis patterns across trials. I did a variety of testing the IMU for calibration and determining key variables that are apparent in someones shot. Some examples include still calibration compared to gravity and rotating it in different directions to understand how the physical movement would correspond to the different sensor axises. This helped me determine which gyroscope axes were most important during the forward wrist snap of a shooting motion.

I created a labeled motion dataset by recording each trial as a CSV file and identifying the movement performed during that trial. I then compared the gyroscope and acceleration patterns across shots, passes, pump fakes, random wrist movements, and stillness. Using those comparisons, I developed rule-based detector that looked for a combination of angular-speed thresholds, axis directions, and consecutive matching samples. The data showed that the real shooting motions were relatively consistent. The main releases produced high angular velocities, with peak total gyroscope measurements generally between approximately 1,400 and 1,700 degrees per second. The Y-axis rotation was strongly negative and was the dominant axis during each recorded shot, while the Z-axis also followed a consistent negative rotation pattern. Requiring the pattern to remain present for several consecutive samples reduced the chance that one brief sensor spike or electrical-noise value would trigger a release candidate. Shooting motions without a ball produced a similar directional pattern, although they generally had lower angular speeds. This showed that the IMU could recognize the general structure of a basketball release and could also measure differences in release intensity - a major development in the project. 

Fixing False Triggers: 

An important learning from this milestone was that total wrist speed alone was not enough to identify a shot. Some random wrist flicks produced angular velocities that were equal to or greater than the real shooting motions. However, those movements usually rotated around different axes or in different directions (imagine flinging your wrist backwards or rapidly raising your hand). Because of this, I developed a preliminary release-candidate detector that considered both the total angular velocity and the directional gyroscope pattern. Rather than triggering from any fast wrist movement, the detector looked for a combination of high total rotation, strongly negative Y-axis rotation, and negative Z-axis rotation over multiple consecutive samples. 

This milestone marked a key paradigm shift. At first, I attempted to make the wrist IMU independently determine whether a shot had occurred. That approach was unreliable because passes, random flicks, pump fakes, and other fast movements could sometimes resemble parts of a shooting motion. While "training" the wrist device maid it way more consistent at detecting shots, nothing in such a small form factor would be perfect.  Instead of confirming a shot by itself, the IMU identified a possible release candidate and measured the mechanics of that movement. The responsibility for confirming what happened to the ball was moved to the hoop module from Milestone 1. The hoop’s piezoelectric sensor detected rim impacts, while the infrared transmitter and receiver detected when the ball passed through the hoop. This sensor-fusion approach was more reliable because the two modules measured different physical events. The wrist module measured what the shooter’s body did, while the hoop module measured what happened when the ball reached the basket.

The completed wrist system produced release-candidate records containing measurements such as:
* Release timestamp (at what time did the ball release)
* Peak total angular velocity (how quickly the wrist rotates in degrees/sec)
* Peak acceleration (combined magnitude of the X, Y, and Z acceleration axes)
* Gyroscope values during the release (combined magnitude of the three gyroscope axes) 
* Dominant rotation axis (when flicking your wrist, what axis changes the most) 
* Approximate duration of the release movement (time where acceleration and gyroscopic values are over a set baseline)

Milestone 2 Outcome: I created a wrist-mounted IMU system that recorded high-speed motion data, identified likely release candidates, and calculated wrist-motion metrics. I also established that the wrist should measure mechanics and propose release candidates, while the hoop should confirm and classify the shot.


# First Milestone - Hoop Module and Make/Miss Classification 

<iframe width="1018" height="572" src="https://www.youtube.com/embed/vPbgvMoHv5M" title="Lochlan M. Milestone 1" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>

For my first milestone, I designed and built the first prototype of the hoop module for my basketball shot analytics system. The prototype originally used a microcontroller mounted to the hoop, an infrared (IR) transmitter and receiver pair, and the piezoelectric vibration sensor attached around the rim.  The IR sensor pair was used to detect when a basketball passed completely through the hoop, confirming a made shot, while the piezoelectric sensor was positioned on the rim to measure the vibrations created by ball impacts. 

MPU-6050 vs Piezoelectric Discs:

Throughout this milestone, I learned how to program and interface with the ESP32 microcontroller. I initially tested the hoop module with an ESP32, then moved to a classic Arduino Nano during early prototyping because it gave me more reliable wired testing. In Milestone 3, I later transferred the working hoop logic to a Nano ESP32 so the module could communicate wirelessly over Bluetooth (see above). To detect vibrations, I originally experimented with an MPU-6050 inertial measurement unit mounted directly to the hoop. Through this testing, I discovered that while the MPU-6050 could reliably detect that an impact had occurred, it was difficult to determine exactly where (and if) the ball struck the rim because vibrations quickly spread throughout the entire hoop. Because of this, I redesigned the sensing approach and transitioned from using multiple MPU-6050 sensors to piezoelectric vibration sensors. 
Piezoelectric discs produced clearer and more sensitive impact signals than the hoop-mounted IMU. However, testing multiple piezo also showed that vibration traveled throughout the metal rim, causing cross-triggering between sensors. Because exact front, back, left, and right impact classification was not consistently reliable, I simplified the final design and used the piezo primarily to determine whether rim contact occurred. 

One of the biggest engineering challenges during this milestone was designing a mounting system that was rigid enough to produce consistent sensor data while still being practical to prototype. I experimented with different mounting locations and attachment methods before determining that securely mounting the sensors to the rigid steel support structure produced more consistent measurements than allowing parts to move independently with the advantage of them being easier to remove. As stated earlier, I had originally attempted to mount the piezo near the front rim (as that is where most players missed), yet it proved the limitations of prototyping on a mini-hoop.

Another challenge came from the internal structure of Piezo Discs. Piezo discs are highly sensitive. When you tap them, they squeeze and turn that physical force into electricity. A light tap might generate 1 Volt. A harder vibration (likes someone shooting a basketball) can easily generate 10+ Volts. This massive spike completely exceeds the Microcontroller Limit because a huge spike exceeds the 5V limit (for a Arudino Nano) or 3.3V limit (for Nano Esp32). Any voltage below this limit is accurately measured. Any voltage above this limit is ignored because the internal hardware physically cannot read any higher. Over time, with continuous high readings it causes the microcontroller to develop internal resistance and could possible damage the board. To solve this, I used a pulldown resistor to prevent voltage spikes over the max reading. 

Milestone 1 Outcome: I created a hoop-mounted system that detected ball passage and rim vibration, filtered duplicate sensor triggers, and classified clean makes, rim-contact makes, and rim misses. Testing also showed that exact rim-impact location could not be measured reliably with the prototype’s vibration sensors.

# Schematics 
Here's where you'll put images of your schematics. [Tinkercad](https://www.tinkercad.com/blog/official-guide-to-tinkercad-circuits) and [Fritzing](https://fritzing.org/learning/) are both great resoruces to create professional schematic diagrams, though BSE recommends Tinkercad becuase it can be done easily and for free in the browser. 

# Code

The final ShotSync system used these five main programs for the wrist module, hoop module, Python analytics system, and web dashboard.

## Wrist Firmware

The wrist firmware runs on the **XIAO nRF52840 Sense**. It reads the onboard LSM6DS3TR-C IMU, identifies possible basketball release motions, records the motion data surrounding the release, then sends that data to the computer using Bluetooth Low Energy.

[View the complete wrist firmware](./ShotSync_XIAO_Wrist_Reliable_BLE.ino)

## Hoop Firmware

The hoop firmware runs on the **Arduino Nano ESP32**. It reads the infrared sensor and piezoelectric vibration sensor, determines whether the shot was a clean make, rim-contact make, or rim miss, then sends the result to the computer over Bluetooth Low Energy.

[View the complete hoop firmware](./HoopDetector_NanoESP32_BLE.ino)

## Python Analytics Integrator

The Python integrator connects to both Bluetooth devices at the same time. It receives the wrist-motion data and hoop events, pairs corresponding events together, calculates wrist-motion metrics, and saves the completed shot data.

[View the complete analytics integrator](./milestone3_wireless_integrator_v5.py)

## ShotSync Dashboard

The dashboard is built using Streamlit. It displays the shot result, wrist mechanics, athlete profiles, shooting statistics, Form Match score, motion graphs, and historical comparisons.

[View the complete dashboard code](./shotsync_dashboard_v4_1.py)

## Launcher

The launcher starts both the Python analytics system and the Streamlit dashboard so that the complete ShotSync system can be started with one command in terminal.

[View the complete launcher](./run_shotsync_wireless.py)


# Bill of Materials
Here's where you'll list the parts in your project. To add more rows, just copy and paste the example rows below.
Don't forget to place the link of where to buy each component inside the quotation marks in the corresponding row after href =. Follow the guide [here]([url](https://www.markdownguide.org/extended-syntax/)) to learn how to customize this to your project needs. 

| **Part** | **Note** | **Price** | **Link** |
|:--:|:--:|:--:|:--:|
| Arduino Nano (w/ headers)| Used for recieving data on the hoop module of the project | 16$ | <a href="https://www.amazon.com/Arduino-Nano-Every-headers-Mounted/dp/B07WWK29XF/ref=sr_1_1_sspa?crid=3DKIZVKPPUTJ5&dib=eyJ2IjoiMSJ9.QmNYvO8VeEYJRoPLV8e0zXTVa4f1jG2BDdr1cCnXe_NMUe0cnJGUNVQjB6oYB2iln1E1oNyQSgx-6_A9dabd7p2yE-hzZO1ecktxCbr83BsKur20VzcGgRSUUnbglxSxU630U7r7hWpRpfH1gmjeSVsl57X8s9mqRdpd4vQM6gDPJXiWq9apDR97_Ilbuuw_AFfWl_SRpNo087y7OG3ED5GbbQh_5VNquPTQJ_q10RwfBc0EhFTdXMu4gar5AELtK7oT9jHIRuKQXpkyREgLiVNRN0i3qWT7WPqdlQ3zfnY.XO4UWMMhCcbbnD6PVHLWQ311DiJdDCBeTcaxr6sI2no&dib_tag=se&keywords=arduino+nano&qid=1783698240&s=electronics&sprefix=arduino+nan%2Celectronics%2C173&sr=1-1-spons&sp_csd=d2lkZ2V0TmFtZT1zcF9hdGY&psc=1)"> Link </a> |
| Breadboard | Connecting wires with ease | $1.17 | <a href="https://www.amazon.com/DEYUE-breadboard-Set-Prototype-Board/dp/B07LFD4LT6/ref=sr_1_4?crid=1NH98FS4SMZ72&dib=eyJ2IjoiMSJ9.AGqrRb490GgIDwzDnYkbxnxXhtfgMK0AP7ANAmSG9esOl5ome8YP1lKRzSphuZ8uUQPUmol5BbWro5FjbPOS5HVLuRymgk7sMgcJPSosOTtbOF7KZRTaQWhM90Bmsmf8_OngYWFyvmG9alLLs0iO8i6FCbZoJ80m3NDgeyYozMcox5wROq-KEOTxvcBiJTtczj0uwu6ETZm5LOMxlCXRC6GQU9XaDx8nBSZo6w6I3oDXuoHX7Kd8kHXGJctvA1yUpl0LufuICdG9Hz6gUYsoCtTFMlDrSf4KtnYDjF3EjTA.N38rgC86gcQ1OlR5q2e9EFMIvTh5lQ-51wReoQ_G_U4&dib_tag=se&keywords=breadboard&qid=1783698369&s=electronics&sprefix=breado%2Celectronics%2C166&sr=1-4)"> Link </a> |
| 27mm Piezoelectric Discs | Sensing vibrations on the hoop, allowing to detect plausible shot attempts | $3.50 | <a href="https://www.amazon.com/TIMESETL-Pickup-Amplifiers-Acoustic-Guitar/dp/B077YJ3H6R/ref=sr_1_3?crid=3U0WHNVI75SGR&dd=ZgXdUxf9VDP6vbCJRhpmnA%2C%2C&dib=eyJ2IjoiMSJ9.jCFAZAdLF_4mM4TXnaG9qSdpmRBesa3laHclmruaEIBx0ekXh4E3Okip34N3B940xievBNFraDntzO3YUC5aGAy0T7XrWkXJSOTve8ZCmU0GWkiMfpC-lTEV8ZhNO721ff9nh6Tl7F_8-jMVJFL9fn4ooRw2W7g_LIQfq1XAR8vWIbFydsg5m_kv9tIaf_t-jxWDJfhRcwfWETCbURZ-Q3Z7uis2DnqoaUwAunm-6UhPuxlvr3enlVysxwLACSQPo-GVaV_KXkRDbxcH--PTC2G8KYVgGOEFKzcG99FbEVQ.i-FASFdoxKKqVNSAatBSc5_QkJjokcjfL1gkG3O5WE8&dib_tag=se&keywords=27+mm+piezo+discs&qid=1783701108&refinements=p_90%3A8308921011&rnid=8308919011&s=musical-instruments&sprefix=27+mm+piezo+discs%2Cmi%2C314&sr=1-3"> Link </a> |
| IR Sensor | Determining if a shot was made | $3.60| <a href="amazon.com/Sensor-Counting-Distance-Through-Beam-Photoelectric/dp/B0FPD2NZPL/ref=sr_1_2_sspa?crid=3OZLL3KZ2SJSH&dib=eyJ2IjoiMSJ9.8xJb67Y_HLSoMBvUTcYhtQF1l5KjlU8Eabev_YjmABcJJxk7oRI_aqAm11cQDtgy7dcxw6t0lfYEHJRf7FZqYzl7LOQoXcXYRFZObz1bXzraBWZ41C7npyqktgVHtpvQ-nVrHrFAzCPB359wfWGBS2g3ZK2FqcPO5oFK27MzgH5JEIYOaGSQt2icwE7B2H6u2sXmjXFSJv3cwi4Jj3r597FH26pP1SNt4NLGVDtUXFg.0dDiDgyDfAiFXiI2L2gD65JDhgo2W9kGzDSWzScoXT8&dib_tag=se&keywords=ir+sensor&qid=1786681496&sprefix=ir+sens%2Caps%2C209&sr=8-2-spons&sp_csd=d2lkZ2V0TmFtZT1zcF9hdGY&psc=1"> Link </a> |
| XIAO Sense SEED Studio | Wrist Analytics Calcuator/Shot Metrics | $13.33 |<a href="https://www.amazon.com/XIAO-MG24-Sense-3PCS-Board/dp/B0F4BTB2NK/ref=sr_1_4?crid=2W2UIH8TW3XC1&dib=eyJ2IjoiMSJ9.c5f_2wL1ztVP3MmsEYn7YNQ1UbbJ9LAqrNTFEIP7_CadezH5mODNMKGG2JdQbEx76d-XPuf1h3Il5FLcWn_lRYTXVclzETo3gRpKkn2OXG5dGn6LyJ7rVCc2vb36apexEHlzKqkmK3GIXDm_5xhnYjgHLZNwOHd-9tMtWQzhV9SFTNwfT5VUOSD-OwQUIXJI7rGCARZsXUf3MRNVLDf_341MPdG3Uimqe1i9po3Dk7U.6F53Xd6Zigg7ILsD5j5UWx2jATNUEly8QdbFfQv1hEo&dib_tag=se&keywords=xiao%2Bsense&qid=1786681593&sprefix=xiao%2Bsense%2Caps%2C218&sr=8-4&th=1"> Link </a>|
| INIU Power Bank | Powe Bank for mini-hoop circuitry | $21.59 |<a href="https://www.amazon.com/INIU-Portable-High-Speed-Flashlight-Compatible/dp/B0CB1FW5FC/ref=sr_1_4?crid=3AYBC7SV08J0&dib=eyJ2IjoiMSJ9.hPmpZ3Dn04aFdcFbHvdfwLN5Q17uj6XyxbXWEh3P8F46pkVShCoNwGrrouxg1dV7cfP4hNrjMB9b0gYeipniOit7rMacACM9OyuwzCufrijb6YQcnfYiIuAGSohSgl9-GA4s41AWhkYzaERm3QnA8Ua9jrc5mkKoCKYAdoowhUq1j4l5eHRiYEKCmptXwKNlYR_L0Jn9V9oPgSGi0hm7_yAb7oqgKI710T1HL7in4VU.G1vUAZTjr-wcQkRmniCp47WTsnrRHkFfSc36zPts38U&dib_tag=se&keywords=iniu%2Bpower%2Bbank&qid=1786681721&sprefix=iniu%2B%2Caps%2C255&sr=8-4&th=1"> Link </a>|
*This may not be the excat model used. I used a power bank from a counselor that may or may not be listed online.
*There where other materials like jumper wires and AAA batteries. These weren't included because of there relative price point and availability respectively.
