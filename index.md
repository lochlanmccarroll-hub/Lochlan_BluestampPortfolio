# Basketball Shot Tracker
ShotSync is a wireless basketball analytics system consisting of a wrist-mounted motion sensor (IMU) and a hoop-mounted outcome detector. It pairs wrist mechanics with shot results and reports measurements such as peak wrist speed, snap duration, follow-through, makes, misses, and shooting percentage. It also determines how consistent someones shot is, a important feature to facilitate improvement. The goal is to give athletes objective data they can use to study the consistency of their shooting motion.

| Lochlan McCarroll | Los Altos High School | Electrical Engineering | Incoming Freshman




  
# Final Milestone

**Don't forget to replace the text below with the embedding for your milestone video. Go to Youtube, click Share -> Embed, and copy and paste the code to replace what's below.**

<iframe width="560" height="315" src="https://www.youtube.com/embed/F7M7imOVGug" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen></iframe>

For your final milestone, explain the outcome of your project. Key details to include are:
- What you've accomplished since your previous milestone
- What your biggest challenges and triumphs were at BSE
- A summary of key topics you learned about
- What you hope to learn in the future after everything you've learned at BSE



# Second Milestone

**Don't forget to replace the text below with the embedding for your milestone video. Go to Youtube, click Share -> Embed, and copy and paste the code to replace what's below.**

<iframe width="560" height="315" src="https://www.youtube.com/embed/y3VAmNlER5Y" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen></iframe>

https://www.youtube.com/watch?v=IMOSZjr0L8E 

### Milestone 2 – Wrist-Sleeve Motion Module

For my second milestone, I designed and built the wrist-sensing module for my basketball shot analytics system. The purpose of this module was to measure the motion of the shooter’s wrist during a release and collect data that could later be compared with the result detected by the hoop module from Milestone 1. The wrist module used an LSM6DS3 inertial measurement unit (IMU) mounted securely to the middle of the back of the shooting wrist, along with an Arduino Nano ESP32 as the temporary development board. 

The IMU measured three-axis linear acceleration and three-axis angular velocity at approximately 104 samples per second. Sampling at approximately 104 Hz meant that the IMU collected a new measurement roughly every 9.6 milliseconds. This was fast enough to capture the short wrist-snap motion and observe how angular velocity changed before, during, and after release. I programmed the system to record the X, Y, and Z acceleration values, total acceleration, X, Y, and Z gyroscope values, total angular velocity, and timestamps. These axis directions depended on the physical orientation of the IMU. I therefore mounted the sensor consistently on the back of the right wrist so that the same shooting motion would produce comparable X-, Y-, and Z-axis patterns across trials. I did a variety of testing the IMU for calibration and determining key variables that are apparent in someones shot. Some examples include still calibration compared to gravity and rotating it in different directions to understand how the physical movement would correspond to the different sensor axises. This helped me determine which gyroscope axes were most important during the forward wrist snap of a shooting motion.

I created a labeled motion dataset by recording each trial as a CSV file and identifying the movement performed during that trial. I then compared the gyroscope and acceleration patterns across shots, passes, pump fakes, random wrist movements, and stillness. Using those comparisons, I developed rule-based detector that looked for a combination of angular-speed thresholds, axis directions, and consecutive matching samples. The data showed that the real shooting motions were relatively consistent. The main releases produced high angular velocities, with peak total gyroscope measurements generally between approximately 1,400 and 1,700 degrees per second. The Y-axis rotation was strongly negative and was the dominant axis during each recorded shot, while the Z-axis also followed a consistent negative rotation pattern. Requiring the pattern to remain present for several consecutive samples reduced the chance that one brief sensor spike or electrical-noise value would trigger a release candidate. Shooting motions without a ball produced a similar directional pattern, although they generally had lower angular speeds. This showed that the IMU could recognize the general structure of a basketball release and could also measure differences in release intensity - a major development in the project. 

An important learning from this milestone was that total wrist speed alone was not enough to identify a shot. Some random wrist flicks produced angular velocities that were equal to or greater than the real shooting motions. However, those movements usually rotated around different axes or in different directions (imagine flinging your wrist backwards or rapidly raising your hand). Because of this, I developed a preliminary release-candidate detector that considered both the total angular velocity and the directional gyroscope pattern. Rather than triggering from any fast wrist movement, the detector looked for a combination of high total rotation, strongly negative Y-axis rotation, and negative Z-axis rotation over multiple consecutive samples. 

This milestone marked a key paradigm shift. At first, I attempted to make the wrist IMU independently determine whether a shot had occurred. That approach was unreliable because passes, random flicks, pump fakes, and other fast movements could sometimes resemble parts of a shooting motion. While "training" the wrist device maid it way more consistent at detecting shots, nothing in such a small form factor would be perfect.  Instead of confirming a shot by itself, the IMU identified a possible release candidate and measured the mechanics of that movement. The responsibility for confirming what happened to the ball was moved to the hoop module from Milestone 1. The hoop’s piezoelectric sensor detected rim impacts, while the infrared transmitter and receiver detected when the ball passed through the hoop. This sensor-fusion approach was more reliable because the two modules measured different physical events. The wrist module measured what the shooter’s body did, while the hoop module measured what happened when the ball reached the basket.

The completed wrist system produced release-candidate records containing measurements such as:
* Release timestamp (at what time did the ball release)
* Peak total angular velocity (how quickly the wrist rotates in degrees/sec)
* Peak acceleration (combined magnitude of the X, Y, and Z acceleration axes)
* Gyroscope values during the release (combined magnitude of the three gyroscope axes) 
* Dominant rotation axis (when flicking your wrist, what axis changes the most) 
* Approximate duration of the release movement (time where acceleration and gyroscopic values are over a set baseline)

The Arduino Nano ESP32 was used as a temporary development platform because it allowed the IMU code and detection algorithm to be tested immediately. The final wearable design was planned around the smaller XIAO nRF52840 Sense, which included an onboard IMU, Bluetooth Low Energy, and battery-charging support. Transferring the system to the XIAO and adding wireless communication were reserved for Milestone 3, when the wrist and hoop modules would be integrated into one complete basketball analytics system.

Milestone 2 Outcome: I created a wrist-mounted IMU system that recorded high-speed motion data, identified likely release candidates, and calculated wrist-motion metrics. I also established that the wrist should measure mechanics and propose release candidates, while the hoop should confirm and classify the shot.

# First Milestone

https://www.youtube.com/watch?v=vPbgvMoHv5M

**Don't forget to replace the text below with the embedding for your milestone video. Go to Youtube, click Share -> Embed, and copy and paste the code to replace what's below.**

<iframe width="560" height="315" src="https://www.youtube.com/embed/CaCazFBhYKs" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen></iframe>

For my first milestone, I designed and built the first prototype of the hoop module for my basketball shot analytics system. The prototype originally used a microcontroller mounted to the hoop, an infrared (IR) transmitter and receiver pair, and the piezoelectric vibration sensor attached around the rim.  The IR sensor pair was used to detect when a basketball passed completely through the hoop, confirming a made shot, while the piezoelectric sensor was positioned on the rim to measure the vibrations created by ball impacts. 

Throughout this milestone, I learned how to program and interface with the ESP32 microcontroller. I initially tested the hoop module with an ESP32, then moved to a classic Arduino Nano during early prototyping because it gave me more reliable wired testing. In Milestone 3, I later transferred the working hoop logic to a Nano ESP32 so the module could communicate wirelessly over Bluetooth (see above). To detect vibrations, I originally experimented with an MPU-6050 inertial measurement unit mounted directly to the hoop. Through this testing, I discovered that while the MPU-6050 could reliably detect that an impact had occurred, it was difficult to determine exactly where (and if) the ball struck the rim because vibrations quickly spread throughout the entire hoop. Because of this, I redesigned the sensing approach and transitioned from using multiple MPU-6050 sensors to piezoelectric vibration sensors. 
Piezoelectric discs produced clearer and more sensitive impact signals than the hoop-mounted IMU. However, testing multiple piezo also showed that vibration traveled throughout the metal rim, causing cross-triggering between sensors. Because exact front, back, left, and right impact classification was not consistently reliable, I simplified the final design and used the piezo primarily to determine whether rim contact occurred. 

One of the biggest engineering challenges during this milestone was designing a mounting system that was rigid enough to produce consistent sensor data while still being practical to prototype. I experimented with different mounting locations and attachment methods before determining that securely mounting the sensors to the rigid steel support structure produced more consistent measurements than allowing parts to move independently with the advantage of them being easier to remove. As stated earlier, I had originally attempted to mount the piezo near the front rim (as that is where most players missed), yet it proved the limitations of prototyping on a mini-hoop.

Another challenge came from the internal structure of Piezo Discs. Piezo discs are highly sensitive. When you tap them, they squeeze and turn that physical force into electricity. A light tap might generate 1 Volt. A harder vibration (likes someone shooting a basketball) can easily generate 10+ Volts. This massive spike completely exceeds the Microcontroller Limit because a huge spike exceeds the 5V limit (for a Arudino Nano) or 3.3V limit (for Nano Esp32). Any voltage below this limit is accurately measured. Any voltage above this limit is ignored because the internal hardware physically cannot read any higher. Over time, with continuous high readings it causes the microcontroller to develop internal resistance and could possible damage the board. To solve this, I used a pulldown resistor to prevent voltage spikes over the max reading. 

Milestone 1 Outcome: I created a hoop-mounted system that detected ball passage and rim vibration, filtered duplicate sensor triggers, and classified clean makes, rim-contact makes, and rim misses. Testing also showed that exact rim-impact location could not be measured reliably with the prototype’s vibration sensors.

# Schematics 
Here's where you'll put images of your schematics. [Tinkercad](https://www.tinkercad.com/blog/official-guide-to-tinkercad-circuits) and [Fritzing](https://fritzing.org/learning/) are both great resoruces to create professional schematic diagrams, though BSE recommends Tinkercad becuase it can be done easily and for free in the browser. 

# Code
Here's where you'll put your code. The syntax below places it into a block of code. Follow the guide [here]([url](https://www.markdownguide.org/extended-syntax/)) to learn how to customize it to your project needs. 

```c++
void setup() {
  // put your setup code here, to run once:
  Serial.begin(9600);
  Serial.println("Hello World!");
}

void loop() {
  // put your main code here, to run repeatedly:

}


# Bill of Materials
Here's where you'll list the parts in your project. To add more rows, just copy and paste the example rows below.
Don't forget to place the link of where to buy each component inside the quotation marks in the corresponding row after href =. Follow the guide [here]([url](https://www.markdownguide.org/extended-syntax/)) to learn how to customize this to your project needs. 

| **Part** | **Note** | **Price** | **Link** |
|:--:|:--:|:--:|:--:|
| Arduino Nano (w/ headers)| Used for recieving data on the hoop module of the project | 16$ | <a href="[https://www.amazon.com/Arduino-A000066-ARDUINO-UNO-R3/dp/B008GRTSV6/](https://www.amazon.com/Arduino-Nano-Every-headers-Mounted/dp/B07WWK29XF/ref=sr_1_1_sspa?crid=3DKIZVKPPUTJ5&dib=eyJ2IjoiMSJ9.QmNYvO8VeEYJRoPLV8e0zXTVa4f1jG2BDdr1cCnXe_NMUe0cnJGUNVQjB6oYB2iln1E1oNyQSgx-6_A9dabd7p2yE-hzZO1ecktxCbr83BsKur20VzcGgRSUUnbglxSxU630U7r7hWpRpfH1gmjeSVsl57X8s9mqRdpd4vQM6gDPJXiWq9apDR97_Ilbuuw_AFfWl_SRpNo087y7OG3ED5GbbQh_5VNquPTQJ_q10RwfBc0EhFTdXMu4gar5AELtK7oT9jHIRuKQXpkyREgLiVNRN0i3qWT7WPqdlQ3zfnY.XO4UWMMhCcbbnD6PVHLWQ311DiJdDCBeTcaxr6sI2no&dib_tag=se&keywords=arduino+nano&qid=1783698240&s=electronics&sprefix=arduino+nan%2Celectronics%2C173&sr=1-1-spons&sp_csd=d2lkZ2V0TmFtZT1zcF9hdGY&psc=1)"> Link </a> |
| Breadboard | Connecting wires with ease | $1.17 | <a href="[https://www.amazon.com/Arduino-A000066-ARDUINO-UNO-R3/dp/B008GRTSV6/](https://www.amazon.com/DEYUE-breadboard-Set-Prototype-Board/dp/B07LFD4LT6/ref=sr_1_4?crid=1NH98FS4SMZ72&dib=eyJ2IjoiMSJ9.AGqrRb490GgIDwzDnYkbxnxXhtfgMK0AP7ANAmSG9esOl5ome8YP1lKRzSphuZ8uUQPUmol5BbWro5FjbPOS5HVLuRymgk7sMgcJPSosOTtbOF7KZRTaQWhM90Bmsmf8_OngYWFyvmG9alLLs0iO8i6FCbZoJ80m3NDgeyYozMcox5wROq-KEOTxvcBiJTtczj0uwu6ETZm5LOMxlCXRC6GQU9XaDx8nBSZo6w6I3oDXuoHX7Kd8kHXGJctvA1yUpl0LufuICdG9Hz6gUYsoCtTFMlDrSf4KtnYDjF3EjTA.N38rgC86gcQ1OlR5q2e9EFMIvTh5lQ-51wReoQ_G_U4&dib_tag=se&keywords=breadboard&qid=1783698369&s=electronics&sprefix=breado%2Celectronics%2C166&sr=1-4)"> Link </a> |
| 27mm Piezoelectric Discs | Sensing vibrations on the hoop, allowing to detect plausible shot attempts | $3.50 | <a href="https://www.amazon.com/TIMESETL-Pickup-Amplifiers-Acoustic-Guitar/dp/B077YJ3H6R/ref=sr_1_3?crid=3U0WHNVI75SGR&dd=ZgXdUxf9VDP6vbCJRhpmnA%2C%2C&dib=eyJ2IjoiMSJ9.jCFAZAdLF_4mM4TXnaG9qSdpmRBesa3laHclmruaEIBx0ekXh4E3Okip34N3B940xievBNFraDntzO3YUC5aGAy0T7XrWkXJSOTve8ZCmU0GWkiMfpC-lTEV8ZhNO721ff9nh6Tl7F_8-jMVJFL9fn4ooRw2W7g_LIQfq1XAR8vWIbFydsg5m_kv9tIaf_t-jxWDJfhRcwfWETCbURZ-Q3Z7uis2DnqoaUwAunm-6UhPuxlvr3enlVysxwLACSQPo-GVaV_KXkRDbxcH--PTC2G8KYVgGOEFKzcG99FbEVQ.i-FASFdoxKKqVNSAatBSc5_QkJjokcjfL1gkG3O5WE8&dib_tag=se&keywords=27+mm+piezo+discs&qid=1783701108&refinements=p_90%3A8308921011&rnid=8308919011&s=musical-instruments&sprefix=27+mm+piezo+discs%2Cmi%2C314&sr=1-3"> Link </a> |

# Other Resources/Examples
One of the best parts about Github is that you can view how other people set up their own work. Here are some past BSE portfolios that are awesome examples. You can view how they set up their portfolio, and you can view their index.md files to understand how they implemented different portfolio components.
- [Example 1](https://trashytuber.github.io/YimingJiaBlueStamp/)
- [Example 2](https://sviatil0.github.io/Sviatoslav_BSE/)
- [Example 3](https://arneshkumar.github.io/arneshbluestamp/)

To watch the BSE tutorial on how to create a portfolio, click here.
