# Basketball Shot Tracker
My project is a complete basletball shot analytics system. Using 2 parts (a hoop module and wrist device) it gives data about a player's shot - with metrics like shot demogrpahics, wrist measurements, and shooting percentages - facilaitating a players improvement with real data to drive real results.


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

For your second milestone, explain what you've worked on since your previous milestone. You can highlight:
- Technical details of what you've accomplished and how they contribute to the final goal
- What has been surprising about the project so far
- Previous challenges you faced that you overcame
- What needs to be completed before your final milestone 

# First Milestone

**Don't forget to replace the text below with the embedding for your milestone video. Go to Youtube, click Share -> Embed, and copy and paste the code to replace what's below.**

<iframe width="560" height="315" src="https://www.youtube.com/embed/CaCazFBhYKs" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen></iframe>

For my first milestone, I designed and built the first prototype of the hoop module for my basketball shot analytics system.  The prototype orignally used an ESP32 microcontroller (Later changed to an arduino nano) mounted to the hoop, an infrared (IR) transmitter and receiver pair, and piezoelectric vibration sensor(s) attached around the rim. The IR sensor pair was used to detect when a basketball passed completely through the hoop, confirming a made shot, while the piezoelectric sensors were positioned around the rim to measure the vibrations created by ball impacts. The long-term goal of these sensors is to help identify where the ball contacted the rim, allowing the system to estimate common miss tendencies such as front rim, back rim, left, or right. 

Throughout this milestone, I learned how to program and interface with the ESP32 microcontroller. Despite not using it for the final design - because of technical difficulites and computer troubles - it was my first experience using the platform. I successfully connected sensors using I²C communication, collected real-time sensor data through the Serial Monitor, and developed software to detect and filter impact events. Before deciding on the final sensing approach, I experimented with an MPU-6050 inertial measurement unit mounted directly to the hoop. This allowed me to study how vibrations through the rim affected the rim after different impacts and helped me better understand the strengths and limitations of using an accelerometer for impact detection. Through this testing, I discovered that while the MPU-6050 could reliably detect that an impact had occurred, it was difficult to determine exactly where the ball struck the rim because vibrations quickly spread throughout the entire hoop. Because of this, I redesigned the sensing approach and transitioned from using multiple MPU-6050 sensors to piezoelectric vibration sensors. Piezoelectric sensors are better suited for detecting localized ( like where the ball actaully strikes) impacts because they respond directly to the strain in the metal near where the ball makes contact. This key difference is due to the fact that the two parts are very different, one being an IMU and the other being  ceramic bonded to a metal brass plate. This simple design change simplified theg hardware while also increasing the likelihood of obtaining useful information about impact location.

One of the biggest engineering challenges during this milestone was designing a mounting system that was rigid enough to produce consistent sensor data while still being practical to prototype. I experimented with different mounting locations and attachment methods before determining that securely mounting the sensors to the rigid steel support structure produced more consistent measurements than allowing parts to move independently with the advantege of them being easier to remove. 

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
