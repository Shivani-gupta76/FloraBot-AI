FloraBOT AI — Final Project Context and Implementation Plan
Use this as the frozen Version 1 plan.
1. Project identity
Project name: FloraBOT AI – Visual Plant Care Assistant
Chatbot name: FloraBOT AI
Tagline: See plant stress. Understand plant care.
Use FloraBOT AI Chatbot in the interface, diagrams and demonstrations.
Zoho SalesIQ should only be mentioned as the underlying implementation platform:
FloraBOT AI is a visual plant-care chatbot built using the Zoho SalesIQ Zobot platform.

2. Project objective
FloraBOT AI allows users to upload a plant photograph. A visual AI model examines visible plant-stress symptoms and provides a cautious watering recommendation.
When watering appears necessary, the FastAPI backend sends an LED1 ON command to an ESP32. When watering does not appear necessary, it sends an LED1 OFF command. The chatbot reports the LED state only after the ESP32 acknowledges the command.
FloraBOT cannot directly measure soil moisture from an image. It must always advise the user to check the soil before watering.
3. Final Version 1 scope
FloraBOT AI will include:
- Welcome screen and chatbot menu
- User-uploaded plant photographs
- JPG, JPEG and PNG support
- Image size and content validation
- Visual plant-stress analysis
- Visible observations and explanation
- Watering recommendation
- Confidence category or uncertainty
- FastAPI backend
- ESP32 Wi-Fi communication
- LED1 ON/OFF control
- ESP32 acknowledgement
- Pending, failed and offline device states
- Retry and upload-another-image options
- Basic plant-care questions
- Error handling
- Testing and documentation
Allowed recommendations
WATERING_RECOMMENDED
WATERING_NOT_RECOMMENDED
UNCERTAIN
No additional result names should be used.
4. Features outside Version 1
Do not add these until the main workflow is complete:
- React dashboard
- Automatic water pump
- Soil-moisture sensor
- User accounts
- Multiple ESP32 devices
- Mobile application
- Plant-history charts
- Redis or Celery
- PostgreSQL
- MQTT
- MobileNetV2
- ESP32-CAM watering assessment
- Disease prediction inside the watering decision
These can be listed as future enhancements.
5. Final system architecture
User
  │
  │ uploads plant photograph
  ▼
FloraBOT AI Chatbot
(Built on Zoho SalesIQ)
  │
  │ secure signed webhook
  ▼
FastAPI Backend
  ├── verifies the chatbot request
  ├── obtains the uploaded image
  ├── validates the image
  ├── returns a pending response
  └── starts background processing
          │
          ▼
Visual AI Plant-Stress Analysis
  ├── confirms that a plant is visible
  ├── checks image quality
  ├── identifies visible stress symptoms
  └── returns structured JSON
          │
          ▼
Backend Decision Validator
  ├── WATERING_RECOMMENDED
  ├── WATERING_NOT_RECOMMENDED
  └── UNCERTAIN
          │
          ▼
ESP32 Command Service
          ▲
          │ authenticated HTTP over Wi-Fi
          ▼
ESP32
  ├── controls LED1
  └── sends acknowledgement
          │
          ▼
FastAPI Backend
  └── completes the chatbot response
          │
          ▼
FloraBOT AI displays the final result
6. Keep the two AI workflows separate
Item	FloraBOT watering assistant	Disease-detection module
Image source	User upload	ESP32-CAM
Analysis	Visual stress assessment	YOLO11n classification
Purpose	Watering assistance	Disease detection
Hardware output	LED1	LED2
Version 1 chatbot scope	Included	Separate


YOLO disease predictions must never determine whether watering is recommended.
7. Chatbot conversation
Welcome message
Hello! Welcome to FloraBOT AI 🌱
I am your Visual Plant Care Assistant. Upload a picture of your plant, and I will examine its visible condition and help you understand whether watering may be needed.

Main menu
- Analyze My Plant
- Plant Care Assistance
- How FloraBOT Works
Image-analysis flow
Analyze My Plant
        ↓
Display photography instructions
        ↓
Request plant image
        ↓
Validate the uploaded file
        ↓
Display “Analyzing your plant…”
        ↓
Run visual AI analysis
        ↓
Display observations and recommendation
        ↓
Create LED1 command when applicable
        ↓
Wait for ESP32 acknowledgement
        ↓
Display confirmed or unconfirmed status
        ↓
Analyze another image / ask a question / finish
Photography instructions
Ask the user to:
- Capture the leaves and overall plant.
- Use adequate lighting.
- Avoid blurred images.
- Keep the plant clearly visible.
- Upload one plant image at a time.
8. Image-upload handling
Accept only:
- JPG
- JPEG
- PNG
Recommended maximum size: 10 MB.
Validate:
- File extension
- MIME type
- Actual image signature
- File size
- Whether the image can be decoded
- Minimum useful dimensions
- Whether a plant is visible
- Whether the image is sufficiently clear
Do not trust the filename alone.
The first development experiment must confirm that the chatbot supplies either the actual file or an authenticated downloadable attachment URL—not only a filename.
9. Asynchronous chatbot processing
AI analysis and ESP32 communication may take longer than the chatbot webhook timeout.
Required process:
1. FloraBOT sends the attachment information to FastAPI.
2. FastAPI validates the signed request.
3. FastAPI creates an analysis job.
4. FastAPI immediately returns a pending response.
5. The image is processed in a background task.
6. FastAPI may send a progress message.
7. FastAPI completes the pending response through the chatbot callback API.
The chatbot must not keep the original webhook request open while waiting for AI and hardware processing.
10. Technology stack
Component	Technology
Chatbot interface	FloraBOT AI
Chatbot platform	Zoho SalesIQ Zobot Webhook platform
Backend	Python FastAPI
Background processing	FastAPI background task
Prototype database	SQLite
Image validation	Pillow or equivalent
Preferred visual model	Qwen3-VL through Ollama, if suitable
AI fallback	Hosted vision-capable API
Hardware	ESP32 and LED1
Device communication	Authenticated HTTP polling
Firmware	Arduino/C++
Backend testing	Pytest
API testing	Postman
Deployment	Public HTTPS server


11. AI-model selection
Use Qwen3-VL through Ollama only if:
- Ollama is available.
- The required model is available.
- The computer has sufficient memory.
- Image input works.
- Structured JSON is reliable.
- Analysis is fast enough.
- Its recommendations pass basic evaluation.
Test it with approximately 10 images:
- Healthy-looking plants
- Visibly wilted plants
- Unclear plants
- Non-plant images
If it performs poorly, use a hosted vision-capable API. The backend should keep the AI provider replaceable.
12. Required AI response format
Conceptually, the AI should return:
{
  "plant_detected": true,
  "image_quality": "GOOD",
  "observations": [
    "The leaves appear visibly drooped",
    "Some leaf edges appear dry"
  ],
  "recommendation": "WATERING_RECOMMENDED",
  "confidence_level": "MEDIUM",
  "explanation": "The plant shows visible symptoms commonly associated with water stress.",
  "suggested_action": "Check whether the soil is dry before watering."
}
Allowed image-quality values:
GOOD
ACCEPTABLE
POOR
Allowed confidence values:
LOW
MEDIUM
HIGH
Use confidence categories instead of presenting an uncalibrated decimal probability.
13. Backend decision rules
The backend validates the AI response before creating a hardware command.
Force UNCERTAIN when:
- No plant is detected.
- Image quality is poor.
- Leaves are not sufficiently visible.
- The image is unrelated or unclear.
- The AI returns invalid JSON.
- Required fields are missing.
- The recommendation is outside the allowed values.
- The AI request fails.
- Visible evidence is conflicting.
The AI is never allowed to directly control the ESP32.
14. Recommendation behaviour
WATERING_RECOMMENDED
- Create an LED1 ON command.
- Advise the user to check whether the soil is dry.
- Wait for ESP32 acknowledgement.
Suggested response:
Your plant shows visible signs that may be associated with water stress. Watering may be helpful, but please check that the soil is dry first.

WATERING_NOT_RECOMMENDED
- Create an LED1 OFF command.
- Advise the user to continue monitoring.
- Wait for ESP32 acknowledgement.
Suggested response:
Your plant does not show clear visible signs that watering is needed right now. Avoid unnecessary watering and continue monitoring it.

UNCERTAIN
- Create no LED command.
- Preserve the existing LED state.
- Ask for a clearer image or manual soil check.
Suggested response:
I could not confidently assess watering needs from this image. Please upload a clearer photograph or manually check the soil. The existing LED state has not been changed.

15. ESP32 communication
Use ESP32-initiated HTTP polling.
Process
1. ESP32 connects to Wi-Fi.
2. ESP32 authenticates with FastAPI.
3. ESP32 checks periodically for a pending command.
4. FastAPI returns no command, LED1 ON or LED1 OFF.
5. ESP32 executes the command.
6. ESP32 sends an acknowledgement.
7. FastAPI matches the acknowledgement with its command ID.
8. FloraBOT displays the confirmed state.
Suggested polling interval: 2–5 seconds.
Each command must contain:
- Unique command ID
- Device ID
- LED name
- Requested state
- Creation time
- Expiry time
Each acknowledgement must contain:
- Command ID
- Device ID
- Success/failure status
- Actual LED state
- Acknowledgement time
Do not claim that the LED is ON or OFF until a matching acknowledgement is received.
16. Chatbot hardware messages
Before acknowledgement:
FloraBOT has requested activation of the watering alert LED.

After acknowledgement:
ESP32 confirmed that the watering alert LED is ON.

ESP32 offline:
The plant recommendation is ready, but the hardware action could not be confirmed.

Failed command:
The plant recommendation is ready, but the ESP32 could not complete the LED action.

Uncertain result:
No new LED command was sent. The previous LED state remains unchanged.

17. Data storage
Analysis information
Store:
- Analysis ID
- Chatbot conversation/reference ID
- Callback request ID
- Image-processing status
- Plant-detected result
- Image quality
- Observations
- Recommendation
- Confidence category
- Explanation
- Suggested action
- Error information
- Creation and completion times
Device-command information
Store:
- Command ID
- Analysis ID
- Device ID
- Requested state
- Command status
- Actual acknowledged state
- Creation time
- Expiry time
- Acknowledgement time
- Failure information
Avoid permanent image storage unless it is required for evaluation and properly documented.
18. Security
Implement:
- Public HTTPS for FastAPI
- Zoho webhook signature verification
- Secure environment variables
- No secrets in chatbot code
- ESP32 device authentication
- Restricted LED1 ON/OFF commands
- File-content and size validation
- Temporary image storage
- Temporary-file deletion
- Duplicate-command protection
- Expired-command rejection
- No credentials in logs
- Basic rate limiting
Do not expose the development server publicly without authentication and HTTPS.
19. Development phases
Phase 0 — Feasibility checks
- Create the FloraBOT test chatbot.
- Test image upload.
- Inspect the attachment payload.
- Download one attachment in FastAPI.
- Test pending and callback responses.
- Check Ollama/Qwen3-VL availability.
- Confirm ESP32-to-FastAPI network communication.
Result: One uploaded image successfully reaches FastAPI and FastAPI can update the conversation.
Phase 1 — Backend with mock analysis
- Create the FastAPI structure.
- Add configuration and SQLite.
- Add signature verification.
- Add image validation.
- Add background processing.
- Return a mock structured result.
Result: FloraBOT receives a mock recommendation for a valid image.
Phase 2 — Visual AI
- Test and select the model.
- Create the visual-analysis prompt.
- Require structured JSON.
- Validate AI responses.
- Add forced-uncertain rules.
- Test healthy, wilted, unclear and non-plant images.
Result: All images produce safe, controlled results.
Phase 3 — ESP32
- Connect ESP32 to Wi-Fi.
- Add authentication.
- Implement command polling.
- Control LED1.
- Send acknowledgements.
- Handle duplicate, expired and failed commands.
Result: The LED changes state and FastAPI receives confirmation.
Phase 4 — Full integration
- Connect image upload, AI, commands and callbacks.
- Add pending and progress messages.
- Add final recommendation formatting.
- Add retry and upload-again options.
- Add basic plant-care assistance.
Result: Complete end-to-end FloraBOT workflow.
Phase 5 — Testing
Test:
- Healthy plant
- Wilted plant
- Unclear image
- Non-plant image
- Invalid file
- Corrupted image
- Oversized image
- Backend unavailable
- AI unavailable
- Invalid AI JSON
- ESP32 offline
- LED1 ON
- LED1 OFF
- Duplicate command
- Uncertain result
- Invalid chatbot signature
- Invalid ESP32 authentication
Phase 6 — Documentation
Prepare:
- Abstract and problem statement
- Objectives and project scope
- Architecture diagram
- Use-case diagram
- Activity diagram
- Sequence diagrams
- Deployment diagram
- Database ER diagram
- ESP32 circuit diagram
- Test-case table
- Results and metrics
- Limitations and future scope
- Screenshots and demonstration video
- Final report and presentation
20. Definition of completion
FloraBOT AI Version 1 is complete when:
- A user can upload a plant image.
- FastAPI receives the actual image.
- Invalid images are rejected.
- Visual AI returns structured results.
- Only the three approved recommendations are possible.
- Unclear images produce UNCERTAIN.
- Uncertain results never change LED1.
- Recommended results request LED1 ON.
- Not-recommended results request LED1 OFF.
- ESP32 acknowledges commands.
- FloraBOT confirms LED state only after acknowledgement.
- Offline hardware is reported honestly.
- Users are told to check the soil.
- Disease detection remains separate.
- Critical tests pass.
- Documentation and demonstration are complete.
21. First implementation milestone
Start with this single vertical workflow:
Upload one image in FloraBOT
        ↓
FastAPI receives the image
        ↓
Mock recommendation is created
        ↓
LED1 command is stored
        ↓
ESP32 retrieves and executes it
        ↓
ESP32 sends acknowledgement
        ↓
FloraBOT displays the confirmed result
After that workflow works, replace the mock recommendation with the real visual AI.


1:06








We need context for building this chatbot, right?







1:07






Worked for 3s







Yes. The plan explains what to build, but we also need a shared implementation context so the chatbot, backend, AI and ESP32 are developed consistently.
We already have the product context. Before coding, we need to confirm these practical details:
1. Existing code
   - Is there already a FastAPI project?
   - Is there existing ESP32 firmware?
   - Which project folder/repository should we use?
2. FloraBOT platform
   - Is the Zoho SalesIQ account ready?
   - Which Zobot builder will be used?
   - Can you access webhook and attachment settings?
3. AI environment
   - Is Ollama installed?
   - Is Qwen3-VL already downloaded?
   - What are the computer’s RAM/GPU specifications?
   - Is a hosted vision API available as fallback?
4. ESP32 setup
   - ESP32 board model
   - LED1 pin number
   - Wi-Fi availability
   - Whether the ESP32 already communicates with FastAPI
   - Existing firmware, if any
5. Deployment
   - Where FastAPI will run
   - Whether a public HTTPS URL already exists
   - Whether this is only a local college demonstration or an internet-accessible system
6. Testing material
   - Healthy plant photographs
   - Wilted plant photographs
   - Unclear photographs
   - Expected recommendation for each test image
7. Chatbot content
   - Preferred language
   - Formal or friendly tone
   - Whether plant-care questions should use AI or predefined answers
   - College/project branding
The best approach is to create a single PROJECT_CONTEXT.md containing:
Project objective
Frozen Version 1 scope
Architecture
Technology choices
Chatbot conversation
AI response format
Decision rules
ESP32 command rules
Security requirements
Testing requirements
Known limitations
Confirmed environment details
Unresolved questions
So, yes: we have enough functional context to understand FloraBOT, but we still need the actual repository, Zoho configuration, AI environment and ESP32 details before implementation can begin safely.
