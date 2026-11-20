"""The demo tenant: a fictional hospital profile with its room tariff.

Used to seed Firestore (``scripts/seed.py``) and the in-memory repository, and by the demo case
generator, so the tariff the engine reads is the same everywhere.
"""

from arzi.domain.models import Hospital, RoomCategory
from arzi.domain.money import rupees

DEMO_HOSPITAL_ID = "sanjeevani-ahd"

DEMO_HOSPITAL = Hospital(
    name="Sanjeevani Multispeciality Hospital",
    city="Ahmedabad",
    room_categories=(
        RoomCategory(name="General ward", rate_per_day=rupees(2_500)),
        RoomCategory(name="Twin sharing", rate_per_day=rupees(4_500)),
        RoomCategory(name="Single private AC", rate_per_day=rupees(8_000)),
    ),
)
