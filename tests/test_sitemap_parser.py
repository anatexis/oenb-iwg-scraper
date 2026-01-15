"""Tests for OeNB sitemap HTML parser."""

import sys
from pathlib import Path

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.sitemap_parser import parse_sitemap_html, get_default_sitemap_path


class TestSitemapParser:
    """Test parsing of OeNB sitemap HTML."""

    def test_parses_sections(self):
        """Test that parser extracts sections from sitemap HTML."""
        path = get_default_sitemap_path()
        if not path.exists():
            pytest.skip("Sitemap HTML not available")
        sections = parse_sitemap_html(str(path))
        assert len(sections) > 0

    def test_section_has_name(self):
        """Test that each section has a name field."""
        path = get_default_sitemap_path()
        if not path.exists():
            pytest.skip("Sitemap HTML not available")
        sections = parse_sitemap_html(str(path))
        assert all("name" in s for s in sections)

    def test_section_has_url(self):
        """Test that each section has a valid URL starting with https://."""
        path = get_default_sitemap_path()
        if not path.exists():
            pytest.skip("Sitemap HTML not available")
        sections = parse_sitemap_html(str(path))
        assert all("url" in s and s["url"].startswith("https://") for s in sections)


class TestExpectedSections:
    """Test that known sections are extracted correctly."""

    def test_statistik_section_exists(self):
        """Test that Statistik section is present."""
        path = get_default_sitemap_path()
        if not path.exists():
            pytest.skip("Sitemap HTML not available")
        sections = parse_sitemap_html(str(path))
        section_names = [s["name"] for s in sections]
        assert "Statistik" in section_names

    def test_ueber_uns_section_exists(self):
        """Test that 'Ueber uns' section is present."""
        path = get_default_sitemap_path()
        if not path.exists():
            pytest.skip("Sitemap HTML not available")
        sections = parse_sitemap_html(str(path))
        section_names = [s["name"] for s in sections]
        # May be "Über uns" with umlaut
        assert any("ber uns" in name for name in section_names)

    def test_sections_have_oenb_urls(self):
        """Test that all URLs point to oenb.at domain."""
        path = get_default_sitemap_path()
        if not path.exists():
            pytest.skip("Sitemap HTML not available")
        sections = parse_sitemap_html(str(path))
        assert all("oenb.at" in s["url"] for s in sections)


class TestSubsections:
    """Test subsection extraction if implemented."""

    def test_section_may_have_subsections(self):
        """Test that sections can optionally have subsections."""
        path = get_default_sitemap_path()
        if not path.exists():
            pytest.skip("Sitemap HTML not available")
        sections = parse_sitemap_html(str(path))
        # At least verify the structure is valid (subsections list if present)
        for section in sections:
            if "subsections" in section:
                assert isinstance(section["subsections"], list)


class TestDefaultPath:
    """Test the default sitemap path function."""

    def test_get_default_sitemap_path_returns_path(self):
        """Test that get_default_sitemap_path returns a Path object."""
        path = get_default_sitemap_path()
        assert isinstance(path, Path)

    def test_default_path_points_to_correct_location(self):
        """Test that default path points to expected location."""
        path = get_default_sitemap_path()
        assert "sitemap" in str(path).lower()
        assert path.name == "Sitemap - Oesterreichische Nationalbank (OeNB).html"
