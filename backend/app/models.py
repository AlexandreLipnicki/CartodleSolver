from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

FIELDS = ('pokedex', 'type', 'stage', 'hp', 'rarity', 'set', 'illustrator')

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Clue(Strict):
    color: Literal['green', 'yellow', 'gray']
    arrow: Literal['up', 'down'] | None = None
    value: str | int | None = None

class Clues(Strict):
    pokedex: Clue
    type: Clue
    stage: Clue
    hp: Clue
    rarity: Clue
    set: Clue
    illustrator: Clue

    @model_validator(mode='after')
    def valid_semantics(self):
        for name in FIELDS:
            c = getattr(self, name)
            if c.color == 'green' and c.arrow:
                raise ValueError(f'{name}: une case verte ne peut pas avoir de flèche')
            if name in ('type', 'stage', 'illustrator') and c.arrow:
                raise ValueError(f'{name}: flèche non prise en charge par les règles')
            if name in ('stage', 'illustrator') and c.color == 'yellow':
                raise ValueError(f'{name}: aucune proximité jaune vérifiée')
        return self

class VisionRow(Strict):
    pokemon: str = Field(min_length=1, max_length=150)
    card_id: str | None = Field(default=None, max_length=100)
    clues: Clues

class VisionResult(Strict):
    rows: list[VisionRow] = Field(min_length=1, max_length=30)

class AttemptInput(Strict):
    card_id: str = Field(min_length=1, max_length=100)
    clues: Clues

class BatchInput(Strict):
    game_id: str = Field(min_length=1,max_length=100)
    attempts: list[AttemptInput] = Field(min_length=1, max_length=30)
    expected_version: int = Field(ge=0)

class LoginInput(Strict):
    code: str = Field(min_length=1, max_length=256)
