// Fixed chat copy. Strings marked in the product spec are used verbatim.

export const WELCOME = [
  "Hello! Welcome to FloraBOT AI 🌱",
  "I am your Visual Plant Care Assistant. Upload a picture of your plant, and I will examine its visible condition and help you understand whether watering may be needed.",
];

export const GREETING = "Hello! What would you like to do?";

export const MENU = [
  { id: "analyze", title: "Analyze My Plant", description: "Check a photo for watering needs", icon: "camera" },
  { id: "care", title: "Plant Care Assistance", description: "Ask about light, soil and watering", icon: "leaf" },
  { id: "how", title: "How FloraBOT Works", description: "See what happens behind the scenes", icon: "gear" },
];

export const PHOTO_INTRO = "Please upload one plant photo (JPG, JPEG or PNG, up to 10 MB). For the best result:";

export const PHOTO_TIPS = [
  "Capture the leaves and overall plant.",
  "Use adequate lighting.",
  "Avoid blurred images.",
  "Keep the plant clearly visible.",
  "Upload one plant image at a time.",
];

export const SOIL_QUESTION = "Have you checked the soil? Push a finger about 2–3 cm into the soil near the stem.";

export const SOIL_REPLIES = {
  WATERING_RECOMMENDED: {
    dry: "Then watering should help. Water slowly until a little drains from the bottom of the pot, and empty the saucer afterwards.",
    moist:
      "Then hold off watering. Drooping leaves with moist soil can mean too much water or root problems. Let the top 2–3 cm dry out and check again tomorrow.",
  },
  WATERING_NOT_RECOMMENDED: {
    dry: "Your plant looks fine, but dry soil means it will need water soon. Water when the top 2–3 cm feel dry.",
    moist: "Great, no water is needed right now. Check the soil again in a few days.",
  },
};

export const CARE_INTRO = "Here are quick answers to common plant-care questions.";

export const CARE_TYPE_HINT = "Or type any plant-care question below.";

export const CARE_TOPICS = [
  {
    question: "How do I check if the soil is dry?",
    answer:
      "Push a finger about 2–3 cm (one knuckle) into the soil near the stem. If it feels dry and crumbly, the plant is ready for water. If it feels cool or damp, wait. For deep pots, a wooden skewer works too: if it comes out clean, the soil is dry.",
  },
  {
    question: "Signs of underwatering",
    answer:
      "- Leaves droop or wilt and perk up after watering\n- Dry, crispy brown leaf edges or tips\n- Soil pulling away from the edge of the pot\n- The pot feels unusually light",
  },
  {
    question: "Signs of overwatering",
    answer:
      "- Yellowing lower leaves\n- Wilting even though the soil is wet\n- Soft, mushy stems or a sour smell from the soil\n- Fungus gnats or mould on the soil surface\n\nOverwatering is more common than underwatering, so always check the soil first.",
  },
  {
    question: "How much light do houseplants need?",
    answer:
      "Most houseplants like bright, indirect light, such as near a window but out of harsh midday sun. Pale, stretched growth means too little light; scorched or bleached patches mean too much. Turn the pot every week or two so it grows evenly.",
  },
  {
    question: "Why are the leaves turning yellow?",
    answer:
      "The most common cause is overwatering, especially when lower leaves turn yellow and the soil stays wet. Other causes are too little light, old leaves naturally dying off, or a lack of nutrients in old soil. Check the soil moisture first before changing anything.",
  },
  {
    question: "General watering tips",
    answer:
      "- Water when the top 2–3 cm of soil are dry, not on a fixed schedule\n- Water thoroughly until a little drains out, then empty the saucer\n- Use pots with drainage holes\n- Plants need less water in winter and in low light",
  },
];

export const HOW_INTRO = "Here is what happens after you send a photo:";

export const HOW_STEPS = [
  { icon: "upload", title: "Upload a photo", detail: "Send one clear photo of your plant from your camera or files." },
  {
    icon: "disease",
    title: "A health check looks for problems",
    detail: "A trained leaf model and an AI review look for diseases and pests.",
  },
  { icon: "scan", title: "AI looks for visible water stress", detail: "A vision model checks the leaves for signs such as drooping or dry edges." },
  {
    icon: "shield",
    title: "FloraBOT checks the result",
    detail: "Every answer ends as Watering recommended, Watering not recommended or Uncertain.",
  },
  {
    icon: "chip",
    title: "The ESP32 sets the watering LED",
    detail: "It turns on when watering is recommended and off when it isn't. Uncertain results leave it unchanged.",
  },
  { icon: "chatCheck", title: "The chat confirms it", detail: "The LED state appears here once the ESP32 reports back." },
];

export const FINISH_MESSAGE = "Thank you for using FloraBOT AI. Happy growing! 🌿";
