from typing import Literal, Set, Tuple

NODE_TYPES = [
    # Objects
    "Entity",  # physical/biological object
    "Signal",  # raw digital readout
    "Derivative",  # computed result
    # Procedures
    "Process",  # any transformation — physical or computational
    "Capture",  # measurement event requiring >=1 Entity input
]

VALID_EDGES: Set[Tuple[str, str]] = {
    # Basic entity transforms
    ("Entity", "Process"),
    ("Process", "Entity"),
    # Signal & derivatives generation from entities
    ("Entity", "Capture"),
    ("Signal", "Capture"),
    ("Derivative", "Capture"),
    ("Capture", "Signal"),
    ("Capture", "Derivative"),
    # signal transforms
    ("Signal", "Process"),
    ("Process", "Signal"),
    # derivative transform
    ("Derivative", "Process"),
    ("Process", "Derivative"),
    # additional rules for simple transforms
    ("Signal", "Derivative"),
}
