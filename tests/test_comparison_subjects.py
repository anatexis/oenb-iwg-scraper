"""Tests for lexical extraction of comparison subjects."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.query_router import extract_comparison_subjects


def test_unterschied_zwischen_x_und_y():
    assert extract_comparison_subjects(
        "Was ist der Unterschied zwischen HVPI und VPI?"
    ) == ["HVPI", "VPI"]


def test_unterscheidet_x_von_y():
    assert extract_comparison_subjects(
        "Was unterscheidet Direktinvestitionen von Portfolioinvestitionen?"
    ) == ["Direktinvestitionen", "Portfolioinvestitionen"]


def test_zwischen_multiword_subjects():
    assert extract_comparison_subjects(
        "Was ist der Unterschied zwischen Basiszinssatz und Leitzins?"
    ) == ["Basiszinssatz", "Leitzins"]


def test_colon_x_oder_y():
    assert extract_comparison_subjects(
        "Bitte vergleiche, welche der beiden Seiten besser zu meiner Frage "
        "passt: Zahlungsbilanz oder Direktinvestitionen."
    ) == ["Zahlungsbilanz", "Direktinvestitionen"]


def test_non_comparison_returns_none():
    assert extract_comparison_subjects("Wo finde ich die Statistik-Hauptseite?") is None


def test_rejects_overlong_subjects():
    # A runaway "und" clause is not a clean comparison — don't split it.
    assert extract_comparison_subjects(
        "Was ist der Unterschied zwischen der langen komplizierten Erklaerung "
        "mit vielen Nebensaetzen und noch mehr Text und einer anderen Sache?"
    ) is None
