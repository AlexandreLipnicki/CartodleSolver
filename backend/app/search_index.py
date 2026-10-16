"""Inverted bitsets: one bit per printing, including unknown metadata buckets."""
import json
from collections import OrderedDict
from threading import RLock


class IndexedCards(list):
    """Immutable-by-convention catalog view; reload the catalog after reindexing."""
    def __init__(self, cards):
        super().__init__(cards)
        self._index = None
        self._lock = RLock()
        self.search_keys = None

    def filtered(self, attempts, by_id):
        with self._lock:
            if self._index is None:
                self._index = CandidateIndex(self)
        return self._index.filtered(attempts, by_id)


class CandidateIndex:
    def __init__(self, cards):
        from .engine import complete
        from .models import FIELDS
        self.cards = cards
        self.all = (1 << len(cards)) - 1
        self.complete = 0
        self.groups = {f: {} for f in FIELDS}
        self.cache = OrderedDict()
        self.lock = RLock()
        for i, c in enumerate(cards):
            bit = 1 << i
            if complete(c):
                self.complete |= bit
            keys = dict(pokedex=tuple(c.get('pokedex') or []), type=tuple(sorted(c.get('types') or [])),
                        hp=c.get('hp'), stage=c.get('stage'), rarity=c.get('rarity'),
                        set=(c.get('set_id'), c.get('series_id'), c.get('release_date')),
                        illustrator=c.get('illustrator'))
            for field, key in keys.items():
                previous = self.groups[field].get(key)
                self.groups[field][key] = (c, (previous[1] if previous else 0) | bit)
        self.valid = [c for c in cards if complete(c)]
        self.uncertain = [c for c in cards if not complete(c)]

    def _mask(self, field, guess, clue, rule_key):
        with self.lock:
            return self._mask_locked(field,guess,clue,rule_key)

    def _mask_locked(self, field, guess, clue, rule_key):
        from .engine import compare
        key = (field, json.dumps(guess,sort_keys=True,separators=(',',':')), clue.color, clue.arrow, rule_key)
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        allowed = 0
        for representative, mask in self.groups[field].values():
            if compare(representative, guess, field, clue) is not False:
                allowed |= mask
        self.cache[key] = allowed
        if len(self.cache) > 512:
            self.cache.popitem(last=False)
        return allowed

    def filtered(self, attempts, by_id):
        from .engine import rules
        from .models import Clues, FIELDS
        if not attempts:
            return list(self.valid), list(self.uncertain)
        remaining = self.all
        # Rules are part of the cache key; server rule changes cannot reuse stale masks.
        rule_key = json.dumps(rules(), sort_keys=True, separators=(',', ':'))
        for attempt in attempts:
            guess = attempt.get('observed_card') or by_id[attempt['card_id']]
            clues = Clues.model_validate(attempt['clues'])
            for field in FIELDS:
                remaining &= self._mask(field, guess, getattr(clues, field), rule_key)
                if not remaining:
                    return [], []
        valid, unknown = [], []
        # Preserve catalog order exactly, including the ordering of incomplete cards.
        while remaining:
            bit = remaining & -remaining
            (valid if self.complete & bit else unknown).append(self.cards[bit.bit_length() - 1])
            remaining ^= bit
        return valid, unknown
