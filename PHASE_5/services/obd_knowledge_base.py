"""
OBD Knowledge Base Service
==========================
Loads the enriched OBD fault-code database (11 000+ codes built from
three real sources: dtc-database, obd-trouble-codes, and dtcdb-master)
and provides fast O(1) lookup for any DTC code.
"""

import json
import os
import pandas as pd
from typing import Optional

_KB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'obd', 'obd_knowledge_base.csv')

# Severity numeric mapping used by the recommendation engine
SEVERITY_RANK = {'Critical': 4, 'High': 3, 'Medium': 2, 'Low': 1, 'Unknown': 0}


class OBDKnowledgeBase:
    """
    Singleton-style knowledge base.  Call OBDKnowledgeBase.get() to obtain the
    shared instance rather than instantiating directly each time.
    """

    _instance: Optional['OBDKnowledgeBase'] = None

    def __init__(self, path: str = _KB_PATH):
        df = pd.read_csv(path)
        df['code'] = df['code'].str.strip().str.upper()
        # Parse stored JSON symptom lists back to Python lists
        df['symptoms'] = df['symptoms'].apply(lambda s: json.loads(s) if isinstance(s, str) else [])
        self._db: dict = df.set_index('code').to_dict(orient='index')

    @classmethod
    def get(cls) -> 'OBDKnowledgeBase':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def lookup(self, code: str) -> dict:
        """
        Return full knowledge-base entry for *code*.
        Returns a synthetic 'Unknown' entry if the code is not in the DB.
        """
        code = code.strip().upper()
        if code in self._db:
            entry = dict(self._db[code])
            entry['code'] = code
            return entry

        # Build a best-effort entry from the code structure alone
        system = self._system_from_prefix(code)
        return {
            'code': code,
            'description': f'Unknown DTC code {code}',
            'severity': 'Unknown',
            'affected_system': system,
            'symptoms': ['Check Engine Light on'],
            'impact': 'Impact unknown — consult a professional mechanic',
            'recommendation': 'Take the vehicle to a qualified technician for diagnosis',
        }

    def lookup_many(self, codes: list[str]) -> list[dict]:
        return [self.lookup(c) for c in codes]

    def max_severity(self, codes: list[str]) -> str:
        """Return the highest severity among a list of codes.
        Returns 'Unknown' for an empty list rather than raising - a
        knowledge-base utility shouldn't crash on missing input, even
        though the current API route happens to guard against this
        case before calling in."""
        if not codes:
            return 'Unknown'
        sevs = [self.lookup(c).get('severity', 'Unknown') for c in codes]
        return max(sevs, key=lambda s: SEVERITY_RANK.get(s, 0))

    def all_codes(self) -> list[str]:
        return list(self._db.keys())

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _system_from_prefix(code: str) -> str:
        if not code:
            return 'Unknown'
        c = code.upper()
        if c.startswith('B'):
            return 'Body'
        if c.startswith('C'):
            return 'Chassis'
        if c.startswith('U'):
            return 'Network/Communication'
        return 'Powertrain'
