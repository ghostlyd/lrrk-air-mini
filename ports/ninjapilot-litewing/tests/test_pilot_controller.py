"""Controller integration uses real session crypto and receiver publication."""
import test_pilot_receiver


class PilotControllerTests(test_pilot_receiver.PilotReceiverTests):
    fixture = "pilot_controller_integration.c"
    extra_sources = ("litewing_pilot_controller.c",)
    cases = ("publish", "stop", "timeout", "fault", "not-neutral", "armed", "busy")
