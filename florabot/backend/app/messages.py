from app.decision import ImageQuality, Recommendation
from app.models import Analysis, Command, CommandStatus, LedState

RECOMMENDATION_MESSAGES = {
    Recommendation.WATERING_RECOMMENDED: (
        "Your plant shows visible signs that may be associated with water stress. "
        "Watering may be helpful, but please check that the soil is dry first."
    ),
    Recommendation.WATERING_NOT_RECOMMENDED: (
        "Your plant does not show clear visible signs that watering is needed right now. "
        "Avoid unnecessary watering and continue monitoring it."
    ),
    Recommendation.UNCERTAIN: (
        "I could not confidently assess watering needs from this image. "
        "Please upload a clearer photograph or manually check the soil. "
        "The existing LED state has not been changed."
    ),
}

# The plan's Uncertain message asks for a clearer photo; these cover the cases where the photo was not the problem.
UNCERTAIN_CLEAR_PHOTO_MESSAGE = (
    "I couldn't tell from this photo whether your plant needs water. "
    "Please check the soil by hand before watering. "
    "The existing LED state has not been changed."
)
UNCERTAIN_NOT_ANALYZED_MESSAGE = (
    "I couldn't analyze this photo right now. "
    "Please try again in a moment, or check the soil by hand. "
    "The existing LED state has not been changed."
)

NO_COMMAND_MESSAGE = "No new LED command was sent. The previous LED state remains unchanged."


def recommendation_message(analysis: Analysis) -> str:
    if analysis.recommendation is not Recommendation.UNCERTAIN:
        return RECOMMENDATION_MESSAGES[analysis.recommendation]
    if analysis.plant_detected is None:
        return UNCERTAIN_NOT_ANALYZED_MESSAGE
    usable_photo = (
        analysis.plant_detected
        and analysis.leaves_visible
        and analysis.image_quality in (ImageQuality.GOOD, ImageQuality.ACCEPTABLE)
    )
    return UNCERTAIN_CLEAR_PHOTO_MESSAGE if usable_photo else RECOMMENDATION_MESSAGES[Recommendation.UNCERTAIN]


def hardware_message(command: Command, device_online: bool, simulated: bool) -> str:
    """Describe the LED command without claiming a state the device has not confirmed."""
    device = "the simulated ESP32" if simulated else "the ESP32"
    match command.status:
        case CommandStatus.PENDING | CommandStatus.DELIVERED:
            action = "activation" if command.requested_state is LedState.ON else "deactivation"
            message = f"FloraBOT has requested {action} of the watering alert LED."
            if not device_online:
                message += f" {device[0].upper()}{device[1:]} has not checked in recently, so this may not be confirmed."
            return message
        case CommandStatus.ACKNOWLEDGED:
            subject = "The simulated ESP32" if simulated else "ESP32"
            return f"{subject} confirmed that the watering alert LED is {command.acknowledged_state}."
        case CommandStatus.FAILED:
            return f"The plant recommendation is ready, but {device} could not complete the LED action."
        case CommandStatus.EXPIRED:
            return "The plant recommendation is ready, but the hardware action could not be confirmed."
        case CommandStatus.SUPERSEDED:
            return f"A newer photo replaced this request before {device} confirmed it."
