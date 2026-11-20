"""FastAPI dependencies.

Collaborators are attached to ``app.state`` by the app factory rather than imported as module
singletons, so tests build an app with fakes and never touch a cloud SDK.
"""

from collections.abc import Sequence
from typing import Annotated

from fastapi import Depends, Request

from arzi.config import Settings
from arzi.services.readiness import ReadinessProbe


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_readiness_probes(request: Request) -> Sequence[ReadinessProbe]:
    probes: Sequence[ReadinessProbe] = request.app.state.readiness_probes
    return probes


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
ReadinessProbesDep = Annotated[Sequence[ReadinessProbe], Depends(get_readiness_probes)]
