"""Authentication adapters. ``demo`` mode signs everyone in as one desk user of the demo hospital;
Firebase ID-token verification arrives in Phase 7 behind the same ``AuthVerifier`` port."""

from arzi.adapters.demo_seed import DEMO_HOSPITAL_ID
from arzi.services.ports import Principal

DEMO_PRINCIPAL = Principal(
    user_id="demo-desk-01",
    display_name="Demo reviewer desk",
    hospital_id=DEMO_HOSPITAL_ID,
    role="reviewer",
)


class DemoAuthVerifier:
    def __init__(self, principal: Principal = DEMO_PRINCIPAL) -> None:
        self._principal = principal

    async def verify(self, authorization: str | None) -> Principal:
        return self._principal
