from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class DataStep:
    name: str
    descr: str

    def __str__(self) -> str:
        return f'["{self.name}" Data Workflow Step ({self.descr})]'

    def __repr__(self) -> str:
        return str(self)


@dataclass
class MDField:
    name: str
    descr: str
    type: str
    values: Optional[List[str]] = None
    block: Optional[DataStep] = None

    def __str__(self) -> str:
        prefix = str(self.block) + " - " if self.block else ""
        return (
            prefix
            + f"\"{self.name}\" field. Description: {self.descr} (The type of field is '{self.type}')"
        )

    def __repr__(self) -> str:
        return str(self)
