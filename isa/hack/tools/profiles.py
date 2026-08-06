from __future__ import annotations

from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROFILE: Final = "hack16"


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    description: str
    word_bits: int = Field(strict=True, gt=0)
    a_immediate_bits: int = Field(strict=True, gt=0)
    address_bits: int = Field(strict=True, gt=0)
    pc_bits: int = Field(strict=True, gt=0)
    rom_words: int = Field(strict=True, gt=0)
    ram_words: int = Field(strict=True, gt=0)
    c_envelope: int = Field(strict=True, ge=0)
    sail_project: Path

    @model_validator(mode="after")
    def validate_architecture(self) -> Profile:
        if self.name not in {"hack16", "hack32"}:
            raise ValueError("Hack profile name must be hack16 or hack32")
        if self.address_bits != 15 or self.pc_bits != 15:
            raise ValueError("Hack profiles retain 15-bit physical addresses")
        if self.rom_words != 32768 or self.ram_words != 32768:
            raise ValueError("Hack profiles retain 32768-word ROM and RAM")
        if self.a_immediate_bits != self.word_bits - 1:
            raise ValueError("A immediate must be one bit narrower than the word")
        if self.word_bits not in {16, 32} or self.word_bits % 4:
            raise ValueError("Hack profile word width must be 16 or 32")
        expected_envelope = 0 if self.word_bits == 16 else 0xFFFF0000
        if self.c_envelope != expected_envelope:
            raise ValueError("C-instruction envelope does not match the word width")
        return self

    @property
    def word_mask(self) -> int:
        return (1 << self.word_bits) - 1

    @property
    def a_immediate_max(self) -> int:
        return (1 << self.a_immediate_bits) - 1

    @property
    def hex_digits(self) -> int:
        return self.word_bits // 4

    def encode_c(self, canonical_hack16_word: int) -> int:
        if not 0xE000 <= canonical_hack16_word <= 0xFFFF:
            raise ValueError("canonical Hack C word must have the 111 prefix")
        return self.c_envelope | canonical_hack16_word


PROFILES: Final[dict[str, Profile]] = {
    "hack16": Profile(
        name="hack16",
        description="canonical nand2tetris Hack 16-bit ISA",
        word_bits=16,
        a_immediate_bits=15,
        address_bits=15,
        pc_bits=15,
        rom_words=32768,
        ram_words=32768,
        c_envelope=0,
        sail_project=PACKAGE_ROOT / "projects/hack16.sail_project",
    ),
    "hack32": Profile(
        name="hack32",
        description="Verylogic Hack 32-bit data-path extension",
        word_bits=32,
        a_immediate_bits=31,
        address_bits=15,
        pc_bits=15,
        rom_words=32768,
        ram_words=32768,
        c_envelope=0xFFFF0000,
        sail_project=PACKAGE_ROOT / "projects/hack32.sail_project",
    ),
}


def get_profile(name: str) -> Profile:
    try:
        return PROFILES[name]
    except KeyError as error:
        available = ", ".join(PROFILES)
        raise ValueError(
            f"unknown Hack profile {name!r}; available: {available}"
        ) from error


def validate_registry() -> None:
    if set(PROFILES) != {"hack16", "hack32"}:
        raise ValueError("Hack registry must contain exactly hack16 and hack32")
    for key, profile in PROFILES.items():
        if key != profile.name or key != key.lower():
            raise ValueError(f"non-canonical Hack profile key: {key!r}")
        if not profile.sail_project.is_file():
            raise ValueError(
                f"profile {key} project does not exist: {profile.sail_project}"
            )


validate_registry()
