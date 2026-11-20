"""Versioned prompt templates, loaded by name and version.

Prompts are code: each lives in ``<name>.v<N>.md`` next to this module, a change is a new
version, and the ``name@vN`` reference is recorded with every model output on the run.
"""

from dataclasses import dataclass
from functools import cache
from importlib.resources import files


@dataclass(frozen=True, slots=True)
class Prompt:
    name: str
    version: int
    text: str

    @property
    def ref(self) -> str:
        return f"{self.name}@v{self.version}"


@cache
def load_prompt(name: str, version: int) -> Prompt:
    resource = files("arzi.prompts").joinpath(f"{name}.v{version}.md")
    if not resource.is_file():
        raise LookupError(f"no prompt {name}.v{version}")
    return Prompt(name=name, version=version, text=resource.read_text(encoding="utf-8").strip())
