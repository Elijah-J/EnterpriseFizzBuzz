"""
Enterprise FizzBuzz Platform - Intellectual Property Office

Provides comprehensive intellectual property protection for the FizzBuzz
ecosystem, including trademark registration with phonetic similarity
analysis (Soundex + Metaphone), patent examination with novelty and
non-obviousness testing, copyright registration with Levenshtein-based
originality scoring, license management with compatibility matrices,
and formal dispute resolution before the FizzBuzz IP Tribunal.

Because "Fizz" is not just a string — it is a registered trademark,
a patented invention, and a copyrightable work of applied modular
arithmetic. The IP Office exists to ensure that every label, every
rule, and every output sequence receives the legal protection it
deserves in a world where divisibility is a competitive advantage.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum, auto
from typing import Any, Optional


# ============================================================
# Enumerations
# ============================================================


class TrademarkStatus(Enum):
    """Status of a trademark application in the registration lifecycle."""
    PENDING = auto()
    REGISTERED = auto()
    OPPOSED = auto()
    EXPIRED = auto()
    CANCELLED = auto()


class PatentStatus(Enum):
    """Status of a patent application in the examination lifecycle."""
    FILED = auto()
    UNDER_EXAMINATION = auto()
    GRANTED = auto()
    REJECTED = auto()
    EXPIRED = auto()


class CopyrightStatus(Enum):
    """Status of a copyright registration."""
    REGISTERED = auto()
    DISPUTED = auto()
    REVOKED = auto()


class LicenseType(Enum):
    """License types available in the FizzBuzz IP ecosystem."""
    FBPL = "FizzBuzz Permissive License"
    FBEL = "FizzBuzz Enterprise License"
    FBCL = "FizzBuzz Copyleft License"


class DisputeVerdict(Enum):
    """Possible verdicts from the IP Tribunal."""
    PLAINTIFF_WINS = auto()
    DEFENDANT_WINS = auto()
    SETTLED = auto()
    DISMISSED = auto()


# ============================================================
# Data Classes
# ============================================================


@dataclass
class TrademarkApplication:
    """A trademark application for a FizzBuzz label."""
    mark: str
    applicant: str
    application_id: str = field(default_factory=lambda: f"TM-{uuid.uuid4().hex[:8].upper()}")
    status: TrademarkStatus = TrademarkStatus.PENDING
    filed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    registered_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    nice_class: int = 42  # Nice Classification Class 42: Scientific instruments
    description: str = ""
    renewal_count: int = 0


@dataclass
class PatentApplication:
    """A patent application for a FizzBuzz rule."""
    title: str
    description: str
    divisor: int
    label: str
    inventor: str
    patent_id: str = field(default_factory=lambda: f"FB-PAT-{uuid.uuid4().hex[:8].upper()}")
    status: PatentStatus = PatentStatus.FILED
    filed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    granted_at: Optional[datetime] = None
    claims: list[str] = field(default_factory=list)
    prior_art_refs: list[str] = field(default_factory=list)
    novelty_score: float = 0.0
    non_obviousness_score: float = 0.0
    utility_score: float = 0.0


@dataclass
class CopyrightRegistration:
    """A copyright registration for a FizzBuzz output work."""
    title: str
    work: str
    author: str
    registration_id: str = field(default_factory=lambda: f"CR-{uuid.uuid4().hex[:8].upper()}")
    status: CopyrightStatus = CopyrightStatus.REGISTERED
    registered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    originality_score: float = 0.0
    license_type: LicenseType = LicenseType.FBPL


@dataclass
class License:
    """A license grant for FizzBuzz intellectual property."""
    license_id: str = field(default_factory=lambda: f"LIC-{uuid.uuid4().hex[:8].upper()}")
    license_type: LicenseType = LicenseType.FBPL
    licensee: str = ""
    ip_reference: str = ""
    granted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    terms: str = ""
    royalty_rate: float = 0.0


@dataclass
class DisputeCase:
    """A dispute case before the FizzBuzz IP Tribunal."""
    case_number: str = field(default_factory=lambda: f"FBIPT-{datetime.now(timezone.utc).year}-{uuid.uuid4().hex[:6].upper()}")
    plaintiff: str = ""
    defendant: str = ""
    dispute_type: str = ""
    subject_matter: str = ""
    filed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    verdict: Optional[DisputeVerdict] = None
    findings_of_fact: list[str] = field(default_factory=list)
    conclusions_of_law: list[str] = field(default_factory=list)
    opinion: str = ""
    damages_awarded: float = 0.0


# ============================================================
# PhoneticSimilarity — Soundex + Metaphone from scratch
# ============================================================


class PhoneticSimilarity:
    """Phonetic similarity engine using Soundex and Metaphone algorithms.

    Implements both algorithms from scratch because importing a library
    for phonetic encoding of FizzBuzz labels would be insufficiently
    enterprise. The similarity score combines both algorithms to catch
    confusingly similar marks like "Fhyzz" vs "Fizz".
    """

    # Soundex consonant mapping
    _SOUNDEX_MAP = {
        'B': '1', 'F': '1', 'P': '1', 'V': '1',
        'C': '2', 'G': '2', 'J': '2', 'K': '2', 'Q': '2',
        'S': '2', 'X': '2', 'Z': '2',
        'D': '3', 'T': '3',
        'L': '4',
        'M': '5', 'N': '5',
        'R': '6',
    }

    @classmethod
    def soundex(cls, word: str) -> str:
        """Compute Soundex code for a word.

        Algorithm:
        1. Retain first letter (uppercased)
        2. Replace consonants with digits per the Soundex map
        3. Remove adjacent duplicates
        4. Remove vowels/H/W/Y (after first letter)
        5. Pad with zeros or truncate to 4 characters
        """
        if not word:
            return "0000"

        word = word.upper()
        # Keep first letter
        result = [word[0]]
        prev_code = cls._SOUNDEX_MAP.get(word[0], '0')

        for ch in word[1:]:
            code = cls._SOUNDEX_MAP.get(ch, '0')
            if code != '0' and code != prev_code:
                result.append(code)
            prev_code = code if code != '0' else prev_code

        # Join, pad/truncate to 4 chars
        soundex_code = ''.join(result)
        return (soundex_code + '0000')[:4]

    @classmethod
    def metaphone(cls, word: str) -> str:
        """Compute Metaphone code for a word.

        A more sophisticated phonetic algorithm that handles:
        - PH -> F, GH -> F (when not at start)
        - Silent letters (K before N, G before N, W before R)
        - CK -> K, SCH -> SK
        - TH -> 0 (theta), SH -> X
        - C -> S before E/I/Y, else K
        - G -> J before E/I/Y, else K
        - Double letters collapsed
        """
        if not word:
            return ""

        word = word.upper()
        # Drop initial silent letter patterns
        if len(word) >= 2:
            if word[:2] in ('AE', 'GN', 'KN', 'PN', 'WR'):
                word = word[1:]

        result = []
        i = 0
        while i < len(word):
            ch = word[i]
            next_ch = word[i + 1] if i + 1 < len(word) else ''
            next2 = word[i + 2] if i + 2 < len(word) else ''

            # Skip duplicate adjacent letters
            if i > 0 and ch == word[i - 1] and ch != 'C':
                i += 1
                continue

            # Vowels: only keep if first character
            if ch in 'AEIOU':
                if i == 0:
                    result.append(ch)
                i += 1
                continue

            if ch == 'B':
                # Silent B after M at end
                if i > 0 and word[i - 1] == 'M' and i == len(word) - 1:
                    i += 1
                    continue
                result.append('B')
            elif ch == 'C':
                if next_ch in 'EIY':
                    result.append('S')
                elif next_ch == 'H':
                    result.append('X')
                    i += 1
                elif next_ch == 'K':
                    i += 1
                    continue
                else:
                    result.append('K')
            elif ch == 'D':
                if next_ch == 'G' and next2 in 'EIY':
                    result.append('J')
                    i += 2
                else:
                    result.append('T')
            elif ch == 'F':
                result.append('F')
            elif ch == 'G':
                if next_ch == 'H' and i + 2 < len(word) and word[i + 2] not in 'AEIOU':
                    # GH silent before consonant
                    i += 2
                    continue
                elif next_ch == 'N' and (i + 2 >= len(word) or (i + 2 < len(word) and word[i + 2] == 'S' and i + 3 >= len(word))):
                    # GN or GNS at end — G is silent
                    i += 1
                    continue
                elif i > 0 and next_ch in 'EIY':
                    result.append('J')
                elif next_ch in 'EIY':
                    result.append('J')
                else:
                    result.append('K')
            elif ch == 'H':
                if next_ch in 'AEIOU' and (i == 0 or word[i - 1] not in 'AEIOU'):
                    result.append('H')
            elif ch == 'J':
                result.append('J')
            elif ch == 'K':
                if i == 0 or word[i - 1] != 'C':
                    result.append('K')
            elif ch == 'L':
                result.append('L')
            elif ch == 'M':
                result.append('M')
            elif ch == 'N':
                result.append('N')
            elif ch == 'P':
                if next_ch == 'H':
                    result.append('F')
                    i += 1
                else:
                    result.append('P')
            elif ch == 'Q':
                result.append('K')
            elif ch == 'R':
                result.append('R')
            elif ch == 'S':
                if next_ch == 'H':
                    result.append('X')
                    i += 1
                elif next_ch == 'C' and next2 == 'H':
                    result.append('SK')
                    i += 2
                elif next_ch == 'I' and next2 in 'AO':
                    result.append('X')
                    i += 2
                else:
                    result.append('S')
            elif ch == 'T':
                if next_ch == 'H':
                    result.append('0')
                    i += 1
                elif next_ch == 'I' and next2 in 'AO':
                    result.append('X')
                    i += 2
                else:
                    result.append('T')
            elif ch == 'V':
                result.append('F')
            elif ch == 'W':
                if next_ch in 'AEIOU':
                    result.append('W')
            elif ch == 'X':
                result.append('KS')
            elif ch == 'Y':
                if next_ch in 'AEIOU':
                    result.append('Y')
            elif ch == 'Z':
                result.append('S')

            i += 1

        return ''.join(result)

    @classmethod
    def similarity(cls, word1: str, word2: str) -> float:
        """Compute phonetic similarity between two words.

        Combines Soundex and Metaphone scores:
        - Soundex match: compare code character by character (0.0-1.0)
        - Metaphone match: longest common subsequence ratio (0.0-1.0)
        - Final score: weighted average (0.4 Soundex + 0.6 Metaphone)

        Returns a float from 0.0 (completely different) to 1.0 (identical).
        """
        if not word1 or not word2:
            return 0.0

        if word1.upper() == word2.upper():
            return 1.0

        # Soundex similarity: character-by-character comparison
        sx1 = cls.soundex(word1)
        sx2 = cls.soundex(word2)
        soundex_matches = sum(1 for a, b in zip(sx1, sx2) if a == b)
        soundex_score = soundex_matches / 4.0

        # Metaphone similarity: LCS ratio
        mp1 = cls.metaphone(word1)
        mp2 = cls.metaphone(word2)
        lcs_len = cls._lcs_length(mp1, mp2)
        max_len = max(len(mp1), len(mp2))
        metaphone_score = lcs_len / max_len if max_len > 0 else 0.0

        return 0.4 * soundex_score + 0.6 * metaphone_score

    @classmethod
    def _lcs_length(cls, s1: str, s2: str) -> int:
        """Compute length of longest common subsequence."""
        m, n = len(s1), len(s2)
        if m == 0 or n == 0:
            return 0
        # Use 1D DP
        prev = [0] * (n + 1)
        for i in range(1, m + 1):
            curr = [0] * (n + 1)
            for j in range(1, n + 1):
                if s1[i - 1] == s2[j - 1]:
                    curr[j] = prev[j - 1] + 1
                else:
                    curr[j] = max(prev[j], curr[j - 1])
            prev = curr
        return prev[n]


# ============================================================
# Levenshtein Distance
# ============================================================


def levenshtein_distance(s1: str, s2: str) -> int:
    """Compute the Levenshtein edit distance between two strings.

    Uses the classic dynamic programming approach because importing
    a library for edit distance computation in a FizzBuzz IP Office
    would be an admission that this problem is trivial. Which it is.
    But we pretend otherwise.
    """
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row
    return prev_row[-1]


def levenshtein_similarity(s1: str, s2: str) -> float:
    """Compute normalized Levenshtein similarity (0.0 = identical, 1.0 = completely different)."""
    max_len = max(len(s1), len(s2))
    if max_len == 0:
        return 0.0
    return levenshtein_distance(s1, s2) / max_len


# ============================================================
# TrademarkRegistry
# ============================================================


class TrademarkRegistry:
    """Registry for FizzBuzz trademarks.

    Maintains a database of registered marks with phonetic similarity
    search to prevent confusingly similar labels from coexisting in
    the FizzBuzz namespace. Pre-seeds the canonical marks FIZZ, BUZZ,
    and FIZZBUZZ because these have been in continuous use since the
    dawn of programming interviews.
    """

    def __init__(
        self,
        similarity_threshold: float = 0.7,
        renewal_days: int = 365,
    ) -> None:
        self._threshold = similarity_threshold
        self._renewal_days = renewal_days
        self._registry: dict[str, TrademarkApplication] = {}
        self._seed_canonical_marks()

    def _seed_canonical_marks(self) -> None:
        """Pre-register the canonical FizzBuzz marks."""
        canonical = [
            ("FIZZ", "FizzBuzz Foundation", "The canonical label for divisibility by 3"),
            ("BUZZ", "FizzBuzz Foundation", "The canonical label for divisibility by 5"),
            ("FIZZBUZZ", "FizzBuzz Foundation", "The canonical combined label for divisibility by 3 and 5"),
        ]
        for mark, applicant, desc in canonical:
            app = TrademarkApplication(
                mark=mark,
                applicant=applicant,
                description=desc,
                status=TrademarkStatus.REGISTERED,
                registered_at=datetime(2007, 1, 1, tzinfo=timezone.utc),
                expires_at=datetime(2099, 12, 31, tzinfo=timezone.utc),
            )
            self._registry[mark.upper()] = app

    def search_similar(self, mark: str) -> list[tuple[str, float]]:
        """Search for trademarks phonetically similar to the given mark.

        Returns a list of (registered_mark, similarity_score) tuples
        for all marks exceeding the similarity threshold.
        """
        results = []
        for registered_mark in self._registry:
            if self._registry[registered_mark].status not in (
                TrademarkStatus.REGISTERED, TrademarkStatus.PENDING
            ):
                continue
            score = PhoneticSimilarity.similarity(mark, registered_mark)
            if score >= self._threshold:
                results.append((registered_mark, score))
        return sorted(results, key=lambda x: -x[1])

    def apply(self, mark: str, applicant: str, description: str = "") -> TrademarkApplication:
        """Apply for trademark registration.

        Performs a similarity search. If confusingly similar marks
        exist, the application is opposed. Otherwise, it is registered.
        """
        # Check for exact match
        if mark.upper() in self._registry:
            existing = self._registry[mark.upper()]
            if existing.status == TrademarkStatus.REGISTERED:
                app = TrademarkApplication(
                    mark=mark.upper(),
                    applicant=applicant,
                    description=description,
                    status=TrademarkStatus.OPPOSED,
                )
                return app

        # Check for similar marks
        similar = self.search_similar(mark)
        if similar:
            app = TrademarkApplication(
                mark=mark.upper(),
                applicant=applicant,
                description=description,
                status=TrademarkStatus.OPPOSED,
            )
            return app

        # Register
        now = datetime.now(timezone.utc)
        app = TrademarkApplication(
            mark=mark.upper(),
            applicant=applicant,
            description=description,
            status=TrademarkStatus.REGISTERED,
            registered_at=now,
            expires_at=now + timedelta(days=self._renewal_days),
        )
        self._registry[mark.upper()] = app
        return app

    def renew(self, mark: str) -> Optional[TrademarkApplication]:
        """Renew a registered trademark."""
        key = mark.upper()
        if key not in self._registry:
            return None
        app = self._registry[key]
        if app.status != TrademarkStatus.REGISTERED:
            return None
        now = datetime.now(timezone.utc)
        app.expires_at = now + timedelta(days=self._renewal_days)
        app.renewal_count += 1
        return app

    def get(self, mark: str) -> Optional[TrademarkApplication]:
        """Get trademark registration details."""
        return self._registry.get(mark.upper())

    @property
    def all_marks(self) -> list[TrademarkApplication]:
        """Return all registered/pending trademarks."""
        return list(self._registry.values())


# ============================================================
# PatentExaminer
# ============================================================


class PatentExaminer:
    """Patent examination engine for FizzBuzz rules.

    Examines patent applications for:
    1. **Novelty**: Does prior art already cover this rule?
    2. **Non-obviousness**: Is the rule sufficiently complex? Uses a
       Kolmogorov complexity heuristic (description length / log2(divisor+1)).
    3. **Utility**: Does the rule produce output for at least one
       integer in the range [1, 1000]?

    Pre-seeds prior art with {3: "Fizz"} and {5: "Buzz"} because
    these inventions are as old as the technical interview itself.
    """

    def __init__(self, novelty_threshold: float = 0.5) -> None:
        self._novelty_threshold = novelty_threshold
        self._patents: list[PatentApplication] = []
        self._prior_art: list[dict[str, Any]] = [
            {"divisor": 3, "label": "Fizz", "source": "Ancient FizzBuzz Manuscript, circa 2007"},
            {"divisor": 5, "label": "Buzz", "source": "Ancient FizzBuzz Manuscript, circa 2007"},
            {"divisor": 15, "label": "FizzBuzz", "source": "Obvious combination of prior art"},
        ]

    def _check_novelty(self, divisor: int, label: str) -> tuple[float, list[str]]:
        """Check if the rule is novel relative to prior art.

        Returns (novelty_score, prior_art_references).
        A score of 1.0 means completely novel; 0.0 means exact prior art match.
        """
        refs = []
        min_distance = float('inf')

        for art in self._prior_art:
            # Compare divisor distance and label similarity
            divisor_distance = abs(divisor - art["divisor"]) / max(divisor, art["divisor"])
            label_sim = PhoneticSimilarity.similarity(label, art["label"])
            combined_distance = 0.5 * divisor_distance + 0.5 * (1.0 - label_sim)

            if combined_distance < min_distance:
                min_distance = combined_distance

            if combined_distance < 0.5:
                refs.append(art["source"])

        novelty = min(min_distance, 1.0)
        return novelty, refs

    def _check_non_obviousness(self, divisor: int, label: str, description: str) -> float:
        """Check non-obviousness using a Kolmogorov complexity heuristic.

        The heuristic estimates information content as:
        score = len(description) / (log2(divisor + 1) * 10 + len(label))

        Higher scores indicate more complex (less obvious) inventions.
        Capped at 1.0.
        """
        import math
        complexity = len(description) / (math.log2(divisor + 1) * 10 + len(label) + 1)
        return min(complexity, 1.0)

    def _check_utility(self, divisor: int) -> float:
        """Check if the rule has utility (produces output for at least one integer).

        A rule with divisor d has utility if there exists any integer n
        in [1, 1000] such that n % d == 0. Since d >= 1 implies d itself
        satisfies this, utility is essentially guaranteed unless d > 1000.
        """
        if divisor <= 0:
            return 0.0
        if divisor <= 1000:
            return 1.0
        return 0.0

    def examine(
        self,
        title: str,
        description: str,
        divisor: int,
        label: str,
        inventor: str = "Anonymous Inventor",
    ) -> PatentApplication:
        """Examine a patent application.

        Applies the three-part test: novelty, non-obviousness, utility.
        If all pass, the patent is granted. Otherwise, it is rejected
        with detailed findings.
        """
        novelty_score, prior_art_refs = self._check_novelty(divisor, label)
        non_obvious_score = self._check_non_obviousness(divisor, label, description)
        utility_score = self._check_utility(divisor)

        app = PatentApplication(
            title=title,
            description=description,
            divisor=divisor,
            label=label,
            inventor=inventor,
            novelty_score=novelty_score,
            non_obviousness_score=non_obvious_score,
            utility_score=utility_score,
            prior_art_refs=prior_art_refs,
            claims=[
                f"A method for evaluating integers by divisibility with respect to {divisor}.",
                f"Wherein the method produces the label '{label}' for qualifying integers.",
                f"The method is applied to all integers in a configurable range.",
            ],
        )

        # All three tests must pass
        if novelty_score < self._novelty_threshold:
            app.status = PatentStatus.REJECTED
        elif non_obvious_score < 0.1:
            app.status = PatentStatus.REJECTED
        elif utility_score < 1.0:
            app.status = PatentStatus.REJECTED
        else:
            app.status = PatentStatus.GRANTED
            app.granted_at = datetime.now(timezone.utc)
            self._prior_art.append({
                "divisor": divisor,
                "label": label,
                "source": f"Patent {app.patent_id}: {title}",
            })

        self._patents.append(app)
        return app

    def get_patent(self, patent_id: str) -> Optional[PatentApplication]:
        """Look up a patent by ID."""
        for p in self._patents:
            if p.patent_id == patent_id:
                return p
        return None

    @property
    def all_patents(self) -> list[PatentApplication]:
        """Return all patent applications."""
        return list(self._patents)

    @property
    def prior_art(self) -> list[dict[str, Any]]:
        """Return the prior art database."""
        return list(self._prior_art)


# ============================================================
# CopyrightRegistry
# ============================================================


class CopyrightRegistry:
    """Registry for FizzBuzz copyrightable works.

    Every FizzBuzz output sequence is a creative work of applied
    modular arithmetic. The Copyright Registry stores these works
    and computes originality scores using Levenshtein distance
    against all previously registered works.
    """

    def __init__(self, originality_threshold: float = 0.3) -> None:
        self._threshold = originality_threshold
        self._works: list[CopyrightRegistration] = []

    def register(
        self,
        title: str,
        work: str,
        author: str = "Anonymous Author",
        license_type: LicenseType = LicenseType.FBPL,
    ) -> CopyrightRegistration:
        """Register a copyrightable work.

        Computes originality score as the minimum Levenshtein similarity
        to any existing registered work. Higher distance = more original.
        """
        if not self._works:
            originality = 1.0
        else:
            min_sim = min(
                levenshtein_similarity(work, w.work) for w in self._works
            )
            # min_sim is distance-based: 0 = identical, 1 = different
            originality = min_sim

        reg = CopyrightRegistration(
            title=title,
            work=work,
            author=author,
            originality_score=originality,
            license_type=license_type,
        )

        if originality < self._threshold:
            reg.status = CopyrightStatus.DISPUTED
        else:
            reg.status = CopyrightStatus.REGISTERED

        self._works.append(reg)
        return reg

    def search(self, query: str) -> list[CopyrightRegistration]:
        """Search registered works by title substring."""
        return [w for w in self._works if query.lower() in w.title.lower()]

    @property
    def all_works(self) -> list[CopyrightRegistration]:
        """Return all registered works."""
        return list(self._works)


# ============================================================
# LicenseManager
# ============================================================


class LicenseManager:
    """License management for FizzBuzz intellectual property.

    Provides three license types with a compatibility matrix:
    - FBPL (FizzBuzz Permissive License): Like MIT. Use freely.
    - FBEL (FizzBuzz Enterprise License): Commercial use requires
      a per-seat FizzBuck royalty payment.
    - FBCL (FizzBuzz Copyleft License): Derivative FizzBuzz works
      must also be licensed under FBCL. Viral, like GPL.

    Compatibility matrix:
                FBPL    FBEL    FBCL
    FBPL        yes     yes     yes
    FBEL        yes     yes     no
    FBCL        yes     no      yes
    """

    # Compatibility matrix: (source, target) -> compatible
    COMPATIBILITY: dict[tuple[LicenseType, LicenseType], bool] = {
        (LicenseType.FBPL, LicenseType.FBPL): True,
        (LicenseType.FBPL, LicenseType.FBEL): True,
        (LicenseType.FBPL, LicenseType.FBCL): True,
        (LicenseType.FBEL, LicenseType.FBPL): True,
        (LicenseType.FBEL, LicenseType.FBEL): True,
        (LicenseType.FBEL, LicenseType.FBCL): False,
        (LicenseType.FBCL, LicenseType.FBPL): True,
        (LicenseType.FBCL, LicenseType.FBEL): False,
        (LicenseType.FBCL, LicenseType.FBCL): True,
    }

    ROYALTY_RATES: dict[LicenseType, float] = {
        LicenseType.FBPL: 0.0,
        LicenseType.FBEL: 0.05,
        LicenseType.FBCL: 0.0,
    }

    def __init__(self) -> None:
        self._licenses: list[License] = []

    def grant(
        self,
        license_type: LicenseType,
        licensee: str,
        ip_reference: str,
        duration_days: int = 365,
    ) -> License:
        """Grant a license for IP usage."""
        now = datetime.now(timezone.utc)
        lic = License(
            license_type=license_type,
            licensee=licensee,
            ip_reference=ip_reference,
            granted_at=now,
            expires_at=now + timedelta(days=duration_days),
            terms=self._generate_terms(license_type),
            royalty_rate=self.ROYALTY_RATES[license_type],
        )
        self._licenses.append(lic)
        return lic

    def check_compatibility(
        self, source: LicenseType, target: LicenseType
    ) -> bool:
        """Check if source license is compatible with target license."""
        return self.COMPATIBILITY.get((source, target), False)

    def _generate_terms(self, license_type: LicenseType) -> str:
        """Generate license terms text."""
        if license_type == LicenseType.FBPL:
            return (
                "Permission is hereby granted, free of charge, to any person "
                "obtaining a copy of this FizzBuzz output, to deal in the output "
                "without restriction, including without limitation the rights to "
                "use, copy, modify, merge, publish, distribute, sublicense, and/or "
                "sell copies of the output. THE OUTPUT IS PROVIDED 'AS IS'."
            )
        elif license_type == LicenseType.FBEL:
            return (
                "This FizzBuzz Enterprise License grants the licensee a "
                "non-exclusive, non-transferable right to use the licensed "
                "FizzBuzz intellectual property for commercial purposes, "
                "subject to a per-evaluation royalty of 0.05 FizzBucks. "
                "Sublicensing requires written approval from the FizzBuzz "
                "IP Office. ENTERPRISE SUPPORT IS NOT INCLUDED."
            )
        else:  # FBCL
            return (
                "This FizzBuzz output is free software: you can redistribute "
                "it and/or modify it under the terms of the FizzBuzz Copyleft "
                "License. Any derivative FizzBuzz works must also be licensed "
                "under FBCL. You must make the source modulo operations available. "
                "THERE IS NO WARRANTY FOR THE FIZZBUZZ, TO THE EXTENT PERMITTED "
                "BY APPLICABLE LAW."
            )

    @property
    def all_licenses(self) -> list[License]:
        """Return all granted licenses."""
        return list(self._licenses)


# ============================================================
# IPDisputeTribunal
# ============================================================


class IPDisputeTribunal:
    """The FizzBuzz Intellectual Property Tribunal.

    Issues formal judicial opinions with case numbers, findings of fact,
    conclusions of law, and damages calculations. All opinions are
    rendered in the absurdly formal style befitting a court that
    adjudicates disputes over the string "Fizz".
    """

    def __init__(self) -> None:
        self._cases: list[DisputeCase] = []

    def file_dispute(
        self,
        plaintiff: str,
        defendant: str,
        dispute_type: str,
        subject_matter: str,
    ) -> DisputeCase:
        """File a dispute before the Tribunal."""
        case = DisputeCase(
            plaintiff=plaintiff,
            defendant=defendant,
            dispute_type=dispute_type,
            subject_matter=subject_matter,
        )
        self._cases.append(case)
        return case

    def adjudicate(self, case: DisputeCase) -> DisputeCase:
        """Adjudicate a dispute and issue a formal opinion.

        The Tribunal's adjudication process involves:
        1. Establishing findings of fact
        2. Applying the relevant FizzBuzz IP law
        3. Issuing conclusions of law
        4. Calculating damages (in FizzBucks)
        5. Rendering a formal written opinion
        """
        # Determine verdict based on dispute type
        if case.dispute_type.lower() == "trademark":
            case = self._adjudicate_trademark(case)
        elif case.dispute_type.lower() == "patent":
            case = self._adjudicate_patent(case)
        elif case.dispute_type.lower() == "copyright":
            case = self._adjudicate_copyright(case)
        else:
            case.verdict = DisputeVerdict.DISMISSED
            case.findings_of_fact = [
                f"The Tribunal received a complaint from {case.plaintiff} "
                f"against {case.defendant}.",
                f"The dispute concerns: {case.subject_matter}.",
                "The Tribunal finds no applicable FizzBuzz IP law governing this matter.",
            ]
            case.conclusions_of_law = [
                "The dispute does not fall within the jurisdiction of this Tribunal.",
                "The case is hereby DISMISSED without prejudice.",
            ]
            case.damages_awarded = 0.0

        case.opinion = self._render_opinion(case)
        return case

    def _adjudicate_trademark(self, case: DisputeCase) -> DisputeCase:
        """Adjudicate a trademark dispute."""
        # Hash-based deterministic ruling for consistency
        h = int(hashlib.md5(case.case_number.encode()).hexdigest()[:8], 16)
        plaintiff_wins = h % 3 != 0  # Plaintiff wins 2/3 of the time

        if plaintiff_wins:
            case.verdict = DisputeVerdict.PLAINTIFF_WINS
            case.findings_of_fact = [
                f"The Plaintiff ({case.plaintiff}) is the owner of the registered "
                f"trademark at issue.",
                f"The Defendant ({case.defendant}) has used a confusingly similar "
                f"mark in commerce.",
                f"The subject matter of this dispute is: {case.subject_matter}.",
                "Consumer confusion is likely given the phonetic similarity of the marks.",
                "The Defendant's mark appears in the same Nice Classification (Class 42: "
                "Scientific and technological services involving modulo arithmetic).",
            ]
            case.conclusions_of_law = [
                "The Defendant's use constitutes trademark infringement under the "
                "FizzBuzz Lanham Act, 15 F.B.C. Section 1114.",
                "The Plaintiff is entitled to injunctive relief and damages.",
                "The Defendant is hereby ORDERED to cease and desist all use of "
                "the infringing mark.",
            ]
            case.damages_awarded = 42000.0
        else:
            case.verdict = DisputeVerdict.DEFENDANT_WINS
            case.findings_of_fact = [
                f"The Plaintiff ({case.plaintiff}) alleges trademark infringement.",
                f"The Defendant ({case.defendant}) has demonstrated that the marks "
                f"are not confusingly similar.",
                f"The subject matter of this dispute is: {case.subject_matter}.",
                "The Tribunal finds insufficient evidence of consumer confusion.",
            ]
            case.conclusions_of_law = [
                "The Plaintiff has failed to establish a likelihood of confusion.",
                "Judgment is entered in favor of the Defendant.",
            ]
            case.damages_awarded = 0.0

        return case

    def _adjudicate_patent(self, case: DisputeCase) -> DisputeCase:
        """Adjudicate a patent dispute."""
        case.verdict = DisputeVerdict.PLAINTIFF_WINS
        case.findings_of_fact = [
            f"The Plaintiff ({case.plaintiff}) holds a valid patent covering "
            f"the method described in the complaint.",
            f"The Defendant ({case.defendant}) has implemented a method that "
            f"falls within the scope of the patent claims.",
            f"The subject matter: {case.subject_matter}.",
            "Claim construction reveals that the Defendant's implementation "
            "performs the same function, in the same way, to achieve the same result.",
            "The doctrine of equivalents applies.",
        ]
        case.conclusions_of_law = [
            "The Defendant has literally infringed Claims 1-3 of the patent.",
            "Under the doctrine of equivalents, the Defendant's implementation "
            "is not meaningfully different from the patented method.",
            "The Plaintiff is awarded damages in the amount of 15 FizzBucks "
            "per infringing evaluation, plus attorney's fees.",
        ]
        case.damages_awarded = 15000.0
        return case

    def _adjudicate_copyright(self, case: DisputeCase) -> DisputeCase:
        """Adjudicate a copyright dispute."""
        case.verdict = DisputeVerdict.SETTLED
        case.findings_of_fact = [
            f"The Plaintiff ({case.plaintiff}) claims copyright in a FizzBuzz "
            f"output sequence.",
            f"The Defendant ({case.defendant}) has produced a substantially "
            f"similar output sequence.",
            f"The subject matter: {case.subject_matter}.",
            "Both parties acknowledge that FizzBuzz output sequences are "
            "determined entirely by mathematical rules and have limited "
            "expressive variation.",
            "The parties have reached a settlement.",
        ]
        case.conclusions_of_law = [
            "The merger doctrine applies: when there is only one way to "
            "express a FizzBuzz evaluation, the expression merges with the idea.",
            "The parties are encouraged to settle and share a FizzBuzz.",
            "The case is SETTLED with mutual licensing under FBPL terms.",
        ]
        case.damages_awarded = 0.0
        return case

    def _render_opinion(self, case: DisputeCase) -> str:
        """Render a formal judicial opinion."""
        border = "=" * 62
        lines = [
            "",
            border,
            "BEFORE THE FIZZBUZZ INTELLECTUAL PROPERTY TRIBUNAL",
            border,
            "",
            f"  Case No.: {case.case_number}",
            f"  Filed:    {case.filed_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "",
            f"  {case.plaintiff},",
            "      Plaintiff,",
            "",
            "    v.",
            "",
            f"  {case.defendant},",
            "      Defendant.",
            "",
            border,
            "  OPINION AND ORDER",
            border,
            "",
            "  I. FINDINGS OF FACT",
            "",
        ]
        for i, fact in enumerate(case.findings_of_fact, 1):
            lines.append(f"    {i}. {fact}")
        lines.append("")
        lines.append("  II. CONCLUSIONS OF LAW")
        lines.append("")
        for i, conclusion in enumerate(case.conclusions_of_law, 1):
            lines.append(f"    {i}. {conclusion}")
        lines.append("")
        lines.append("  III. ORDER")
        lines.append("")

        if case.verdict == DisputeVerdict.PLAINTIFF_WINS:
            lines.append("    Judgment is ENTERED in favor of the Plaintiff.")
            lines.append(f"    Damages awarded: {case.damages_awarded:,.2f} FizzBucks.")
        elif case.verdict == DisputeVerdict.DEFENDANT_WINS:
            lines.append("    Judgment is ENTERED in favor of the Defendant.")
            lines.append("    The Plaintiff's complaint is DENIED.")
        elif case.verdict == DisputeVerdict.SETTLED:
            lines.append("    The case is SETTLED by agreement of the parties.")
            lines.append("    Each party shall bear its own costs.")
        else:
            lines.append("    The case is DISMISSED without prejudice.")

        lines.append("")
        lines.append("  SO ORDERED.")
        lines.append("")
        lines.append("  _______________________________")
        lines.append("  The Honorable Judge Modulo")
        lines.append("  FizzBuzz Intellectual Property Tribunal")
        lines.append("")
        lines.append(border)
        lines.append("")
        return "\n".join(lines)

    @property
    def all_cases(self) -> list[DisputeCase]:
        """Return all dispute cases."""
        return list(self._cases)


# ============================================================
# IPOfficeDashboard
# ============================================================


class IPOfficeDashboard:
    """ASCII dashboard for the FizzBuzz Intellectual Property Office.

    Renders a comprehensive overview of trademark registrations,
    patent grants, copyright registrations, license portfolio,
    and pending disputes.
    """

    @staticmethod
    def render(
        trademark_registry: TrademarkRegistry,
        patent_examiner: PatentExaminer,
        copyright_registry: CopyrightRegistry,
        license_manager: LicenseManager,
        tribunal: IPDisputeTribunal,
        width: int = 60,
    ) -> str:
        """Render the IP Office dashboard."""
        border = "+" + "-" * (width - 2) + "+"
        title_line = "| FIZZBUZZ INTELLECTUAL PROPERTY OFFICE"
        title_line = title_line + " " * (width - 1 - len(title_line)) + "|"

        lines = [
            "",
            border,
            title_line,
            "| Trademarks | Patents | Copyrights | Licenses | Disputes" + " " * max(0, width - 60) + " |",
            border,
        ]

        # Trademark Portfolio
        lines.append("")
        lines.append("  TRADEMARK PORTFOLIO")
        lines.append("  " + "-" * (width - 4))
        trademarks = trademark_registry.all_marks
        if trademarks:
            for tm in trademarks:
                status_icon = {
                    TrademarkStatus.REGISTERED: "[R]",
                    TrademarkStatus.PENDING: "[P]",
                    TrademarkStatus.OPPOSED: "[!]",
                    TrademarkStatus.EXPIRED: "[X]",
                    TrademarkStatus.CANCELLED: "[-]",
                }.get(tm.status, "[?]")
                line = f"  {status_icon} {tm.mark:<20} {tm.applicant:<20} {tm.status.name}"
                lines.append(line[:width])
        else:
            lines.append("  (no trademarks registered)")

        # Patent Portfolio
        lines.append("")
        lines.append("  PATENT PORTFOLIO")
        lines.append("  " + "-" * (width - 4))
        patents = patent_examiner.all_patents
        if patents:
            for pat in patents:
                status_icon = {
                    PatentStatus.GRANTED: "[G]",
                    PatentStatus.FILED: "[F]",
                    PatentStatus.UNDER_EXAMINATION: "[E]",
                    PatentStatus.REJECTED: "[X]",
                    PatentStatus.EXPIRED: "[-]",
                }.get(pat.status, "[?]")
                line = f"  {status_icon} {pat.patent_id}  d={pat.divisor}->'{pat.label}'  N={pat.novelty_score:.2f}"
                lines.append(line[:width])
        else:
            lines.append("  (no patents filed)")

        # Copyright Portfolio
        lines.append("")
        lines.append("  COPYRIGHT PORTFOLIO")
        lines.append("  " + "-" * (width - 4))
        copyrights = copyright_registry.all_works
        if copyrights:
            for cr in copyrights:
                status_icon = "[C]" if cr.status == CopyrightStatus.REGISTERED else "[D]"
                line = f"  {status_icon} {cr.registration_id}  '{cr.title}'  orig={cr.originality_score:.2f}"
                lines.append(line[:width])
        else:
            lines.append("  (no copyrights registered)")

        # License Portfolio
        lines.append("")
        lines.append("  LICENSE PORTFOLIO")
        lines.append("  " + "-" * (width - 4))
        licenses = license_manager.all_licenses
        if licenses:
            for lic in licenses:
                line = f"  [{lic.license_type.name}] {lic.license_id}  -> {lic.licensee}"
                lines.append(line[:width])
        else:
            lines.append("  (no licenses granted)")

        # Disputes
        lines.append("")
        lines.append("  DISPUTE DOCKET")
        lines.append("  " + "-" * (width - 4))
        cases = tribunal.all_cases
        if cases:
            for c in cases:
                verdict_str = c.verdict.name if c.verdict else "PENDING"
                line = f"  {c.case_number}  {c.plaintiff} v. {c.defendant}  [{verdict_str}]"
                lines.append(line[:width])
        else:
            lines.append("  (no disputes filed)")

        # Summary statistics
        lines.append("")
        lines.append("  " + "-" * (width - 4))
        registered_tm = sum(1 for t in trademarks if t.status == TrademarkStatus.REGISTERED)
        granted_pat = sum(1 for p in patents if p.status == PatentStatus.GRANTED)
        registered_cr = sum(1 for c in copyrights if c.status == CopyrightStatus.REGISTERED)
        lines.append(f"  Trademarks: {registered_tm} registered | "
                     f"Patents: {granted_pat} granted | "
                     f"Copyrights: {registered_cr}")
        lines.append(f"  Licenses: {len(licenses)} active | "
                     f"Disputes: {len(cases)} filed")
        lines.append("")
        lines.append(border)
        lines.append("")

        return "\n".join(lines)
