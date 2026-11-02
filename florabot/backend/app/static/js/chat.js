import { initThemeToggle } from "./chat/theme-toggle.js";
import { initConnectDialog } from "./chat/connect.js";
import { initModelPicker } from "./chat/ai-models.js";
import { startHardwareStatus } from "./chat/hardware.js";
import { initComposer } from "./chat/composer.js";
import { analyzePhoto } from "./chat/analysis.js";
import { handleText, welcome } from "./chat/flows.js";

initThemeToggle();
initConnectDialog();
initModelPicker();
startHardwareStatus();
initComposer({ onText: handleText, onAnalyze: analyzePhoto });
welcome();
