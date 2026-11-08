"""Minimal FiberLab troubleshooting guides (Stage 3 replaces this with RAG)."""

GUIDES = {
    "no_service": [
        "Check that the ONT (white box from FiberLab) has its power light on and the PON light steady.",
        "Check that the network cable between the ONT and the router is firmly connected at both ends.",
        "Restart the WiFi router: unplug it for 30 seconds and plug it back in.",
    ],
    "slow_internet": [
        "Test the speed with a device connected by cable to the router to rule out WiFi.",
        "Move closer to the router or use the 5 GHz network for faster WiFi.",
        "Pause downloads, updates or streaming on other devices during the test.",
    ],
    "wifi": [
        "Place the router in a central, elevated spot, away from walls, mirrors and microwaves.",
        "Connect to the 5 GHz network when close to the router; use 2.4 GHz for longer range.",
        "Restart the router to pick a less crowded WiFi channel.",
    ],
}


def steps_for(intent: str, attempt: int) -> list[str]:
    """Return the guide steps for this attempt (later attempts go deeper)."""
    steps = GUIDES.get(intent, GUIDES["no_service"])
    return steps if attempt == 0 else steps[1:] + steps[:1]
