from typing import Literal, Set, Tuple

NODE_TYPES = [
    # Objects
    "Entity",  # physical/biological object
    "Signal",  # raw digital readout
    "Derivative",  # computed result
    # Procedures
    "Process",  # any transformation — physical or computational
    "Capture",  # measurement event requiring >=1 Entity input
    # Additional wrappers for objects and procedures
    "Condition",  # environmental context, annotation only
    "Hardware",  # physical instrument agent
    "Software",  # computational agent
    "Provenance",  # administrative metadata wrapper
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
    # ??? skip process if its too easy to describe (but maybe we don't need to skip because of proc description)
    ("Signal", "Derivative"),
    # derivative transform
    ("Derivative", "Process"),
    ("Process", "Derivative"),
    # H&S specific wrappers on procedures
    ("Hardware", "Capture"),
    ("Hardware", "Process"),
    ("Software", "Process"),
    ("Condition", "Process"),
    ("Condition", "Capture"),
    ("Condition", "Entity"),
    # Provenance wrappers for
    ("Provenance", "Entity"),
    ("Provenance", "Signal"),
    ("Provenance", "Derivative"),
}
