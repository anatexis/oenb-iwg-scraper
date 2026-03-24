import json
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scraper"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.export_knowledge_base_jsonl import (
    _build_family_chunk_text,
    _latest_observation,
    _latest_observations_by_series,
    export_knowledge_base_jsonl,
)
from oenb_scraper.asset_store import store_asset_document
from oenb_scraper.database import init_db, start_crawl_run, store_page, store_resource_link
from oenb_scraper.isaweb_store import (
    store_isaweb_dataset,
    store_isaweb_meta_response,
    store_isaweb_observations,
    store_isaweb_page_context,
)


def test_export_knowledge_base_jsonl_includes_pages_assets_and_isaweb():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "pages.db"
        output_path = Path(tmpdir) / "knowledge_base.jsonl"
        conn = init_db(db_path)
        run_id = start_crawl_run(conn, "https://www.oenb.at/", "TestBot/1.0")

        page_id = store_page(
            conn,
            run_id=run_id,
            url="https://www.oenb.at/en/Statistics/Standardized-Tables.html",
            final_url="https://www.oenb.at/en/Statistics/Standardized-Tables.html",
            status_code=200,
            content_type="text/html",
            body=b"<html><body>Statistics overview</body></html>",
        )
        conn.execute(
            """
            INSERT INTO page_content (page_id, title, text_content, page_section, language, extracted_at, extractor_version)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                page_id,
                "Standardized Tables",
                "Statistics overview page",
                "Statistics",
                "en",
                "2026-03-19T10:00:00Z",
                "page-extractor-v1",
            ),
        )

        asset_page_id = store_page(
            conn,
            run_id=run_id,
            url="https://www.oenb.at/downloads/leitzins.csv",
            final_url="https://www.oenb.at/downloads/leitzins.csv",
            status_code=200,
            content_type="text/csv",
            body=b"period;value\n2026-01;2.50\n2026-02;2.75\n",
        )
        store_asset_document(
            conn,
            page_id=asset_page_id,
            url="https://www.oenb.at/downloads/leitzins.csv",
            content_type="text/csv",
            body=b"period;value\n2026-01;2.50\n2026-02;2.75\n",
        )
        store_resource_link(
            conn,
            source_url="https://www.oenb.at/en/Statistics/Standardized-Tables.html",
            target_url="https://www.oenb.at/downloads/leitzins.csv",
            normalized_target_url="https://www.oenb.at/downloads/leitzins.csv",
            link_text="Leitzins CSV",
            section_heading="Interest rates",
            resource_kind="asset_document",
            embed_type="item",
        )

        dataset_id = store_isaweb_dataset(
            conn,
            hierid=321,
            lang="EN",
            pos=["VDBFKBSC217000"],
            dimensions={"dval1": ["AT"]},
            freq="M",
            title="Base rates",
            source_url="https://www.oenb.at/isawebstat/dynabfrage/showResult?hierid=321&lang=EN&pos=VDBFKBSC217000&dval1=AT&freq=M",
        )
        store_isaweb_observations(
            conn,
            dataset_id=dataset_id,
            observations=[
                {"period": "2026-01", "value": "2.50", "unit": "%", "series_label": "Base rates"},
                {"period": "2026-02", "value": "2.75", "unit": "%", "series_label": "Base rates"},
            ],
        )
        store_isaweb_page_context(
            conn,
            source_url="https://www.oenb.at/en/Statistics/Standardized-Tables.html",
            target_url="https://www.oenb.at/isawebstat/stabfrage/createReport?report=3.21.1&lang=EN",
            link_text="Base rates",
            section_heading="Interest rates",
            relation_kind="isaweb_entry",
        )
        store_isaweb_meta_response(
            conn,
            response_url="https://www.oenb.at/isadataservice/meta?lang=EN&hierid=321&pos=VDBFKBSC217000",
            xml_text="""<?xml version="1.0" encoding="UTF-8"?>
            <metainfo>
              <header>
                <prepared>2026-03-19T10:12:54Z</prepared>
                <sender id="AT2">
                  <name>Oesterreichische Nationalbank</name>
                </sender>
                <last_update>2026-03-19T10:12:54Z</last_update>
              </header>
              <meta>
                <title>Base rates</title>
                <unit>Percent</unit>
                <comment>Policy rates overview.</comment>
                <frequency>month</frequency>
                <data_available><data>2024 - 2026</data></data_available>
                <last_update>2026-03-19 08:02:12</last_update>
                <source>OeNB, ECB</source>
                <lag>-</lag>
                <releases>
                  <release><release_date>Week 16/2026</release_date><reference>March 2026</reference><revision></revision></release>
                </releases>
              </meta>
            </metainfo>
            """,
        )

        exported = export_knowledge_base_jsonl(db_path, output_path)

        lines = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
        by_type = {line["record_type"]: line for line in lines if line["record_type"] != "release_event"}
        release_records = [line for line in lines if line["record_type"] == "release_event"]

        assert exported == 9
        assert by_type["page_document"]["title"] == "Standardized Tables"
        assert by_type["asset_document"]["asset_type"] == "csv"
        assert by_type["asset_document"]["linked_from"][0]["source_url"] == "https://www.oenb.at/en/Statistics/Standardized-Tables.html"
        assert by_type["isaweb_dataset"]["title"] == "Base rates"
        assert by_type["isaweb_dataset"]["latest_observation"]["value"] == "2.75"
        assert by_type["isaweb_dataset"]["page_contexts"][0]["source_url"] == "https://www.oenb.at/en/Statistics/Standardized-Tables.html"
        assert by_type["isaweb_metadata"]["title"] == "Base rates"
        assert by_type["isaweb_metadata"]["source"] == "OeNB, ECB"
        assert release_records[0]["release_date_text"] == "Week 16/2026"


def test_export_knowledge_base_jsonl_includes_grouped_dataset_family_record():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "pages.db"
        output_path = Path(tmpdir) / "knowledge_base.jsonl"
        conn = init_db(db_path)
        run_id = start_crawl_run(conn, "https://www.oenb.at/", "TestBot/1.0")

        page_id = store_page(
            conn,
            run_id=run_id,
            url="https://www.oenb.at/en/Statistics/Standardized-Tables/Interest-rates/Base-and-reference-rates.html",
            final_url="https://www.oenb.at/en/Statistics/Standardized-Tables/Interest-rates/Base-and-reference-rates.html",
            status_code=200,
            content_type="text/html",
            body=b"<html><body>Base and reference rates</body></html>",
        )
        conn.execute(
            """
            INSERT INTO page_content (page_id, title, text_content, page_section, language, extracted_at, extractor_version)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                page_id,
                "Base and reference rates",
                "Source: OeNB, ECB. Statistics page for base and reference rates.",
                "Statistics",
                "en",
                "2026-03-19T10:00:00Z",
                "page-extractor-v1",
            ),
        )

        asset_page_id = store_page(
            conn,
            run_id=run_id,
            url="https://www.oenb.at/downloads/base-rates.csv",
            final_url="https://www.oenb.at/downloads/base-rates.csv",
            status_code=200,
            content_type="text/csv",
            body=b"period;value\n2026-01;2.50\n2026-02;2.75\n",
        )
        store_asset_document(
            conn,
            page_id=asset_page_id,
            url="https://www.oenb.at/downloads/base-rates.csv",
            content_type="text/csv",
            body=b"period;value\n2026-01;2.50\n2026-02;2.75\n",
        )
        store_resource_link(
            conn,
            source_url="https://www.oenb.at/en/Statistics/Standardized-Tables/Interest-rates/Base-and-reference-rates.html",
            target_url="https://www.oenb.at/downloads/base-rates.csv",
            normalized_target_url="https://www.oenb.at/downloads/base-rates.csv",
            link_text="Download CSV",
            section_heading="Base and reference rates",
            resource_kind="asset_document",
            embed_type="item",
        )

        dataset_id = store_isaweb_dataset(
            conn,
            hierid=321,
            lang="EN",
            pos=["VDBFKBSC217000"],
            dimensions={"dval1": ["AT"]},
            freq="M",
            title="Base rates",
            source_url="https://www.oenb.at/isadataservice/data?lang=EN&hierid=321&pos=VDBFKBSC217000&dval1=AT&freq=M",
        )
        store_isaweb_observations(
            conn,
            dataset_id=dataset_id,
            observations=[
                {"period": "2026-01", "value": "2.50", "unit": "%", "series_label": "Base rates"},
                {"period": "2026-02", "value": "2.75", "unit": "%", "series_label": "Base rates"},
            ],
        )
        store_isaweb_page_context(
            conn,
            source_url="https://www.oenb.at/en/Statistics/Standardized-Tables/Interest-rates/Base-and-reference-rates.html",
            target_url="https://www.oenb.at/isawebstat/stabfrage/createReport?report=3.21.1&lang=EN",
            link_text="Base rates",
            section_heading="Base and reference rates",
            relation_kind="isaweb_entry",
        )
        store_isaweb_meta_response(
            conn,
            response_url="https://www.oenb.at/isadataservice/meta?lang=EN&hierid=321&pos=VDBFKBSC217000",
            xml_text="""<?xml version="1.0" encoding="UTF-8"?>
            <metainfo>
              <header>
                <prepared>2026-03-19T10:12:54Z</prepared>
                <sender id="AT2">
                  <name>Oesterreichische Nationalbank</name>
                </sender>
                <last_update>2026-03-19T10:12:54Z</last_update>
              </header>
              <meta>
                <title>Base rates</title>
                <unit>Percent</unit>
                <comment>Policy rates overview.</comment>
                <frequency>month</frequency>
                <data_available><data>2024 - 2026</data></data_available>
                <last_update>2026-03-19 08:02:12</last_update>
                <source>OeNB, ECB</source>
                <lag>-</lag>
                <releases>
                  <release><release_date>Week 16/2026</release_date><reference>March 2026</reference><revision></revision></release>
                </releases>
              </meta>
            </metainfo>
            """,
        )

        export_knowledge_base_jsonl(db_path, output_path)

        lines = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
        family_records = [line for line in lines if line["record_type"] == "dataset_family"]

        assert len(family_records) == 1
        family = family_records[0]
        assert family["title"] == "Base rates"
        assert family["latest_observation"] == {
            "period": "2026-02",
            "value": "2.75",
            "unit": "%",
            "series_label": "Base rates",
        }
        assert family["source_page"]["url"] == (
            "https://www.oenb.at/en/Statistics/Standardized-Tables/Interest-rates/Base-and-reference-rates.html"
        )
        assert family["asset_documents"][0]["url"] == "https://www.oenb.at/downloads/base-rates.csv"
        assert family["isaweb_dataset"]["dataset_key"].startswith("hierid=321|lang=EN")
        assert family["isaweb_metadata"]["meta_key"] == "hierid=321|lang=EN|pos=VDBFKBSC217000"
        assert family["release_events"][0]["release_date_text"] == "Week 16/2026"


def test_export_knowledge_base_jsonl_groups_supporting_statistics_pages_into_dataset_family():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "pages.db"
        output_path = Path(tmpdir) / "knowledge_base.jsonl"
        conn = init_db(db_path)
        run_id = start_crawl_run(conn, "https://www.oenb.at/", "TestBot/1.0")

        topic_page_id = store_page(
            conn,
            run_id=run_id,
            url="https://www.oenb.at/en/Statistics/Standardized-Tables/Interest-rates.html",
            final_url="https://www.oenb.at/en/Statistics/Standardized-Tables/Interest-rates.html",
            status_code=200,
            content_type="text/html",
            body=b"<html><body>Interest rates topic</body></html>",
        )
        conn.execute(
            """
            INSERT INTO page_content (page_id, title, text_content, page_section, language, extracted_at, extractor_version)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                topic_page_id,
                "Interest rates and exchange rates",
                "Topic page for standardized tables.",
                "Statistics",
                "en",
                "2026-03-19T10:00:00Z",
                "page-extractor-v1",
            ),
        )

        main_page_url = "https://www.oenb.at/en/Statistics/Standardized-Tables/Interest-rates/Base-and-reference-rates.html"
        main_page_id = store_page(
            conn,
            run_id=run_id,
            url=main_page_url,
            final_url=main_page_url,
            status_code=200,
            content_type="text/html",
            body=b"<html><body>Base and reference rates</body></html>",
        )
        conn.execute(
            """
            INSERT INTO page_content (page_id, title, text_content, page_section, language, extracted_at, extractor_version)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                main_page_id,
                "Base and reference rates",
                "Statistics page for base and reference rates.",
                "Statistics",
                "en",
                "2026-03-19T10:00:00Z",
                "page-extractor-v1",
            ),
        )

        note_page_url = "https://www.oenb.at/en/Statistics/Standardized-Tables/Interest-rates/Base-and-reference-rates/Explanatory-notes.html"
        note_page_id = store_page(
            conn,
            run_id=run_id,
            url=note_page_url,
            final_url=note_page_url,
            status_code=200,
            content_type="text/html",
            body=b"<html><body>Explanatory notes</body></html>",
        )
        conn.execute(
            """
            INSERT INTO page_content (page_id, title, text_content, page_section, language, extracted_at, extractor_version)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                note_page_id,
                "Explanatory notes",
                "Methodological notes for base rates.",
                "Statistics",
                "en",
                "2026-03-19T10:00:00Z",
                "page-extractor-v1",
            ),
        )

        release_page_url = "https://www.oenb.at/en/Statistics/Standardized-Tables/Release-calendar.html"
        release_page_id = store_page(
            conn,
            run_id=run_id,
            url=release_page_url,
            final_url=release_page_url,
            status_code=200,
            content_type="text/html",
            body=b"<html><body>Release calendar</body></html>",
        )
        conn.execute(
            """
            INSERT INTO page_content (page_id, title, text_content, page_section, language, extracted_at, extractor_version)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                release_page_id,
                "Release calendar",
                "Scheduled publication dates for standardized tables.",
                "Statistics",
                "en",
                "2026-03-19T10:00:00Z",
                "page-extractor-v1",
            ),
        )

        store_resource_link(
            conn,
            source_url="https://www.oenb.at/en/Statistics/Standardized-Tables/Interest-rates.html",
            target_url=main_page_url,
            normalized_target_url=main_page_url,
            link_text="Base and reference rates",
            section_heading="Interest rates",
            resource_kind="page_document",
            embed_type="item",
        )
        store_resource_link(
            conn,
            source_url=main_page_url,
            target_url=note_page_url,
            normalized_target_url=note_page_url,
            link_text="Explanatory notes",
            section_heading="Base and reference rates",
            resource_kind="page_document",
            embed_type="item",
        )
        store_resource_link(
            conn,
            source_url=main_page_url,
            target_url=release_page_url,
            normalized_target_url=release_page_url,
            link_text="Release calendar",
            section_heading="Base and reference rates",
            resource_kind="page_document",
            embed_type="item",
        )

        dataset_id = store_isaweb_dataset(
            conn,
            hierid=321,
            lang="EN",
            pos=["VDBFKBSC217000"],
            dimensions={"dval1": ["AT"]},
            freq="M",
            title="Base rates",
            source_url="https://www.oenb.at/isadataservice/data?lang=EN&hierid=321&pos=VDBFKBSC217000&dval1=AT&freq=M",
        )
        store_isaweb_observations(
            conn,
            dataset_id=dataset_id,
            observations=[
                {"period": "2026-02", "value": "2.75", "unit": "%", "series_label": "Base rates"},
            ],
        )
        store_isaweb_page_context(
            conn,
            source_url=main_page_url,
            target_url="https://www.oenb.at/isawebstat/stabfrage/createReport?report=3.21.1&lang=EN",
            link_text="Base rates",
            section_heading="Base and reference rates",
            relation_kind="isaweb_entry",
        )
        store_isaweb_meta_response(
            conn,
            response_url="https://www.oenb.at/isadataservice/meta?lang=EN&hierid=321&pos=VDBFKBSC217000",
            xml_text="""<?xml version="1.0" encoding="UTF-8"?>
            <metainfo>
              <meta>
                <title>Base rates</title>
                <source>OeNB, ECB</source>
                <releases>
                  <release><release_date>Week 16/2026</release_date><reference>March 2026</reference><revision></revision></release>
                </releases>
              </meta>
            </metainfo>
            """,
        )

        export_knowledge_base_jsonl(db_path, output_path)

        lines = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
        family = next(line for line in lines if line["record_type"] == "dataset_family")
        supporting_titles = {page["title"] for page in family["supporting_pages"]}

        assert family["source_page"]["title"] == "Base and reference rates"
        assert supporting_titles == {
            "Interest rates and exchange rates",
            "Explanatory notes",
            "Release calendar",
        }


def test_export_knowledge_base_jsonl_groups_shared_asset_statistics_context_into_dataset_family():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "pages.db"
        output_path = Path(tmpdir) / "knowledge_base.jsonl"
        conn = init_db(db_path)
        run_id = start_crawl_run(conn, "https://www.oenb.at/", "TestBot/1.0")

        main_page_url = "https://www.oenb.at/en/Statistics/Standardized-Tables/Interest-rates/Base-and-reference-rates.html"
        companion_page_url = "https://www.oenb.at/en/Statistics/Standardized-Tables/Interest-rates/Methodological-overview.html"
        asset_url = "https://www.oenb.at/downloads/base-rates.csv"

        main_page_id = store_page(
            conn,
            run_id=run_id,
            url=main_page_url,
            final_url=main_page_url,
            status_code=200,
            content_type="text/html",
            body=b"<html><body>Base and reference rates</body></html>",
        )
        conn.execute(
            """
            INSERT INTO page_content (page_id, title, text_content, page_section, language, extracted_at, extractor_version)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                main_page_id,
                "Base and reference rates",
                "Statistics page for base and reference rates.",
                "Statistics",
                "en",
                "2026-03-19T10:00:00Z",
                "page-extractor-v1",
            ),
        )

        companion_page_id = store_page(
            conn,
            run_id=run_id,
            url=companion_page_url,
            final_url=companion_page_url,
            status_code=200,
            content_type="text/html",
            body=b"<html><body>Methodological overview</body></html>",
        )
        conn.execute(
            """
            INSERT INTO page_content (page_id, title, text_content, page_section, language, extracted_at, extractor_version)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                companion_page_id,
                "Methodological overview",
                "Background page for base and reference rates with download references.",
                "Statistics",
                "en",
                "2026-03-19T10:00:00Z",
                "page-extractor-v1",
            ),
        )

        asset_page_id = store_page(
            conn,
            run_id=run_id,
            url=asset_url,
            final_url=asset_url,
            status_code=200,
            content_type="text/csv",
            body=b"period;value\n2026-01;2.50\n2026-02;2.75\n",
        )
        store_asset_document(
            conn,
            page_id=asset_page_id,
            url=asset_url,
            content_type="text/csv",
            body=b"period;value\n2026-01;2.50\n2026-02;2.75\n",
        )
        store_resource_link(
            conn,
            source_url=main_page_url,
            target_url=asset_url,
            normalized_target_url=asset_url,
            link_text="Download CSV",
            section_heading="Base and reference rates",
            resource_kind="asset_document",
            embed_type="item",
        )
        store_resource_link(
            conn,
            source_url=companion_page_url,
            target_url=asset_url,
            normalized_target_url=asset_url,
            link_text="Data download",
            section_heading="Methodology",
            resource_kind="asset_document",
            embed_type="item",
        )

        dataset_id = store_isaweb_dataset(
            conn,
            hierid=321,
            lang="EN",
            pos=["VDBFKBSC217000"],
            dimensions={"dval1": ["AT"]},
            freq="M",
            title="Base rates",
            source_url="https://www.oenb.at/isadataservice/data?lang=EN&hierid=321&pos=VDBFKBSC217000&dval1=AT&freq=M",
        )
        store_isaweb_observations(
            conn,
            dataset_id=dataset_id,
            observations=[
                {"period": "2026-02", "value": "2.75", "unit": "%", "series_label": "Base rates"},
            ],
        )
        store_isaweb_page_context(
            conn,
            source_url=main_page_url,
            target_url="https://www.oenb.at/isawebstat/stabfrage/createReport?report=3.21.1&lang=EN",
            link_text="Base rates",
            section_heading="Base and reference rates",
            relation_kind="isaweb_entry",
        )
        store_isaweb_meta_response(
            conn,
            response_url="https://www.oenb.at/isadataservice/meta?lang=EN&hierid=321&pos=VDBFKBSC217000",
            xml_text="""<?xml version="1.0" encoding="UTF-8"?>
            <metainfo>
              <meta>
                <title>Base rates</title>
                <source>OeNB, ECB</source>
              </meta>
            </metainfo>
            """,
        )

        export_knowledge_base_jsonl(db_path, output_path)

        lines = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
        family = next(line for line in lines if line["record_type"] == "dataset_family")
        supporting_titles = {page["title"] for page in family["supporting_pages"]}

        assert family["source_page"]["title"] == "Base and reference rates"
        assert "Methodological overview" in supporting_titles


def test_export_knowledge_base_jsonl_includes_family_sources_and_chatbot_chunk():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "pages.db"
        output_path = Path(tmpdir) / "knowledge_base.jsonl"
        conn = init_db(db_path)
        run_id = start_crawl_run(conn, "https://www.oenb.at/", "TestBot/1.0")

        main_page_url = "https://www.oenb.at/en/Statistics/Standardized-Tables/Interest-rates/Base-and-reference-rates.html"
        note_page_url = "https://www.oenb.at/en/Statistics/Standardized-Tables/Interest-rates/Base-and-reference-rates/Explanatory-notes.html"

        main_page_id = store_page(
            conn,
            run_id=run_id,
            url=main_page_url,
            final_url=main_page_url,
            status_code=200,
            content_type="text/html",
            body=b"<html><body>Base and reference rates</body></html>",
        )
        conn.execute(
            """
            INSERT INTO page_content (page_id, title, text_content, page_section, language, extracted_at, extractor_version)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                main_page_id,
                "Base and reference rates",
                "Source: OeNB, Statistics Austria. Reporting institutions: Statistics Austria.",
                "Statistics",
                "en",
                "2026-03-19T10:00:00Z",
                "page-extractor-v1",
            ),
        )

        note_page_id = store_page(
            conn,
            run_id=run_id,
            url=note_page_url,
            final_url=note_page_url,
            status_code=200,
            content_type="text/html",
            body=b"<html><body>Explanatory notes</body></html>",
        )
        conn.execute(
            """
            INSERT INTO page_content (page_id, title, text_content, page_section, language, extracted_at, extractor_version)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                note_page_id,
                "Explanatory notes",
                "Source: Eurostat. Definitions and methodological background.",
                "Statistics",
                "en",
                "2026-03-19T10:00:00Z",
                "page-extractor-v1",
            ),
        )

        store_resource_link(
            conn,
            source_url=main_page_url,
            target_url=note_page_url,
            normalized_target_url=note_page_url,
            link_text="Explanatory notes",
            section_heading="Base and reference rates",
            resource_kind="page_document",
            embed_type="item",
        )

        dataset_id = store_isaweb_dataset(
            conn,
            hierid=321,
            lang="EN",
            pos=["VDBFKBSC217000"],
            dimensions={"dval1": ["AT"]},
            freq="M",
            title="Base rates",
            source_url="https://www.oenb.at/isadataservice/data?lang=EN&hierid=321&pos=VDBFKBSC217000&dval1=AT&freq=M",
        )
        store_isaweb_observations(
            conn,
            dataset_id=dataset_id,
            observations=[
                {"period": "2026-02", "value": "2.75", "unit": "%", "series_label": "Base rates"},
            ],
        )
        store_isaweb_page_context(
            conn,
            source_url=main_page_url,
            target_url="https://www.oenb.at/isawebstat/stabfrage/createReport?report=3.21.1&lang=EN",
            link_text="Base rates",
            section_heading="Base and reference rates",
            relation_kind="isaweb_entry",
        )
        store_isaweb_meta_response(
            conn,
            response_url="https://www.oenb.at/isadataservice/meta?lang=EN&hierid=321&pos=VDBFKBSC217000",
            xml_text="""<?xml version="1.0" encoding="UTF-8"?>
            <metainfo>
              <meta>
                <title>Base rates</title>
                <comment>Policy rates overview.</comment>
                <source>OeNB, ECB</source>
              </meta>
            </metainfo>
            """,
        )

        export_knowledge_base_jsonl(db_path, output_path)

        lines = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
        family = next(line for line in lines if line["record_type"] == "dataset_family")
        chunk = next(line for line in lines if line["record_type"] == "chatbot_chunk")

        assert family["sources"] == ["OeNB", "Statistics Austria", "ECB"]
        assert family["reporting_institutions"] == ["Statistics Austria"]
        assert chunk["parent_id"] == family["id"]
        assert "Base rates" in chunk["text"]
        assert "2026-02 = 2.75 %" in chunk["text"]
        assert "Sources: OeNB; Statistics Austria; ECB" in chunk["text"]


def test_export_knowledge_base_jsonl_filters_series_labels_out_of_family_sources():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "pages.db"
        output_path = Path(tmpdir) / "knowledge_base.jsonl"
        conn = init_db(db_path)
        run_id = start_crawl_run(conn, "https://www.oenb.at/", "TestBot/1.0")

        page_url = "https://www.oenb.at/en/Statistics/Standardized-Tables/interest-rates-and-exchange-rates/key-interest-rates.html"
        report_url = "https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=10.4"

        page_id = store_page(
            conn,
            run_id=run_id,
            url=page_url,
            final_url=page_url,
            status_code=200,
            content_type="text/html",
            body=b"<html><body>Key interest rates</body></html>",
        )
        conn.execute(
            """
            INSERT INTO page_content (page_id, title, text_content, page_section, language, extracted_at, extractor_version)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                page_id,
                "International key interest rates",
                "Source: Eurostat, Denmark, Sweden, Bulgaria, Macrobond.",
                "Statistics",
                "en",
                "2026-03-20T00:00:00Z",
                "page-extractor-v1",
            ),
        )

        dataset_id = store_isaweb_dataset(
            conn,
            hierid=10,
            lang="EN",
            pos="REPORT:10.4",
            dimensions={},
            freq="A",
            title="Key interest rates",
            source_url=report_url,
        )
        store_isaweb_observations(
            conn,
            dataset_id=dataset_id,
            observations=[
                {"period": "2025", "value": "2.15", "unit": "%", "series_label": "Euro area"},
                {"period": "2025", "value": "1.75", "unit": "%", "series_label": "Denmark"},
                {"period": "2025", "value": "1.75", "unit": "%", "series_label": "Sweden"},
            ],
        )
        store_isaweb_page_context(
            conn,
            source_url=page_url,
            target_url=report_url,
            link_text="Table",
            section_heading="Key interest rates",
            relation_kind="isaweb_entry",
        )

        export_knowledge_base_jsonl(db_path, output_path)

        lines = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
        family = next(
            line
            for line in lines
            if line["record_type"] == "dataset_family" and line["title"] == "Key interest rates"
        )

        assert family["sources"] == ["Eurostat", "Macrobond"]


def test_export_knowledge_base_jsonl_includes_isaweb_and_asset_chatbot_chunks():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "pages.db"
        output_path = Path(tmpdir) / "knowledge_base.jsonl"
        conn = init_db(db_path)
        run_id = start_crawl_run(conn, "https://www.oenb.at/", "TestBot/1.0")

        page_url = "https://www.oenb.at/en/Statistics/Standardized-Tables/Interest-rates/Base-and-reference-rates.html"
        asset_url = "https://www.oenb.at/downloads/base-rates.csv"

        page_id = store_page(
            conn,
            run_id=run_id,
            url=page_url,
            final_url=page_url,
            status_code=200,
            content_type="text/html",
            body=b"<html><body>Base and reference rates</body></html>",
        )
        conn.execute(
            """
            INSERT INTO page_content (page_id, title, text_content, page_section, language, extracted_at, extractor_version)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                page_id,
                "Base and reference rates",
                "Statistics page for base rates.",
                "Statistics",
                "en",
                "2026-03-19T10:00:00Z",
                "page-extractor-v1",
            ),
        )

        asset_page_id = store_page(
            conn,
            run_id=run_id,
            url=asset_url,
            final_url=asset_url,
            status_code=200,
            content_type="text/csv",
            body=b"period;value\n2026-01;2.50\n2026-02;2.75\n",
        )
        store_asset_document(
            conn,
            page_id=asset_page_id,
            url=asset_url,
            content_type="text/csv",
            body=b"period;value\n2026-01;2.50\n2026-02;2.75\n",
        )
        store_resource_link(
            conn,
            source_url=page_url,
            target_url=asset_url,
            normalized_target_url=asset_url,
            link_text="Download CSV",
            section_heading="Base and reference rates",
            resource_kind="asset_document",
            embed_type="item",
        )

        dataset_id = store_isaweb_dataset(
            conn,
            hierid=321,
            lang="EN",
            pos=["VDBFKBSC217000"],
            dimensions={"dval1": ["AT"]},
            freq="M",
            title="Base rates",
            source_url="https://www.oenb.at/isadataservice/data?lang=EN&hierid=321&pos=VDBFKBSC217000&dval1=AT&freq=M",
        )
        store_isaweb_observations(
            conn,
            dataset_id=dataset_id,
            observations=[
                {"period": "2026-01", "value": "2.50", "unit": "%", "series_label": "Base rates"},
                {"period": "2026-02", "value": "2.75", "unit": "%", "series_label": "Base rates"},
            ],
        )
        store_isaweb_page_context(
            conn,
            source_url=page_url,
            target_url="https://www.oenb.at/isawebstat/stabfrage/createReport?report=3.21.1&lang=EN",
            link_text="Base rates",
            section_heading="Base and reference rates",
            relation_kind="isaweb_entry",
        )
        store_isaweb_meta_response(
            conn,
            response_url="https://www.oenb.at/isadataservice/meta?lang=EN&hierid=321&pos=VDBFKBSC217000",
            xml_text="""<?xml version="1.0" encoding="UTF-8"?>
            <metainfo>
              <meta>
                <title>Base rates</title>
                <comment>Policy rates overview.</comment>
                <source>OeNB, ECB</source>
              </meta>
            </metainfo>
            """,
        )

        export_knowledge_base_jsonl(db_path, output_path)

        lines = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
        isaweb_chunk = next(
            line for line in lines
            if line["record_type"] == "chatbot_chunk" and line["chunk_kind"] == "isaweb_dataset_summary"
        )
        asset_chunk = next(
            line for line in lines
            if line["record_type"] == "chatbot_chunk" and line["chunk_kind"] == "asset_document_summary"
        )

        assert isaweb_chunk["title"] == "Base rates"
        assert isaweb_chunk["text"].startswith("ISAweb dataset: Base rates.")
        assert "Latest observation: 2026-02 = 2.75 %" in isaweb_chunk["text"]
        assert isaweb_chunk["reference_urls"][0].startswith("https://www.oenb.at/isadataservice/data")

        assert asset_chunk["title"] == "Download CSV"
        assert asset_chunk["text"].startswith("Asset document: Download CSV.")
        assert "Type: csv." in asset_chunk["text"]
        assert "2026-01 | 2.50" in asset_chunk["text"]
        assert asset_chunk["reference_urls"] == [asset_url]


def test_chatbot_chunk_records_prioritize_dataset_and_structured_assets_over_pdfs():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "pages.db"
        output_path = Path(tmpdir) / "knowledge_base.jsonl"
        conn = init_db(db_path)
        run_id = start_crawl_run(conn, "https://www.oenb.at/", "TestBot/1.0")

        page_url = "https://www.oenb.at/en/Statistics/Standardized-Tables/Interest-rates/Base-and-reference-rates.html"
        csv_url = "https://www.oenb.at/downloads/base-rates.csv"
        pdf_url = "https://www.oenb.at/downloads/base-rates-background.pdf"

        page_id = store_page(
            conn,
            run_id=run_id,
            url=page_url,
            final_url=page_url,
            status_code=200,
            content_type="text/html",
            body=b"<html><body>Base and reference rates</body></html>",
        )
        conn.execute(
            """
            INSERT INTO page_content (page_id, title, text_content, page_section, language, extracted_at, extractor_version)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                page_id,
                "Base and reference rates",
                "Statistics page for base rates.",
                "Statistics",
                "en",
                "2026-03-19T10:00:00Z",
                "page-extractor-v1",
            ),
        )

        csv_page_id = store_page(
            conn,
            run_id=run_id,
            url=csv_url,
            final_url=csv_url,
            status_code=200,
            content_type="text/csv",
            body=b"period;value\n2026-01;2.50\n2026-02;2.75\n",
        )
        store_asset_document(
            conn,
            page_id=csv_page_id,
            url=csv_url,
            content_type="text/csv",
            body=b"period;value\n2026-01;2.50\n2026-02;2.75\n",
        )
        store_resource_link(
            conn,
            source_url=page_url,
            target_url=csv_url,
            normalized_target_url=csv_url,
            link_text="Download CSV",
            section_heading="Base and reference rates",
            resource_kind="asset_document",
            embed_type="item",
        )

        pdf_page_id = store_page(
            conn,
            run_id=run_id,
            url=pdf_url,
            final_url=pdf_url,
            status_code=200,
            content_type="application/pdf",
            body=b"%PDF-1.4 broken-but-good-enough-for-test",
        )
        store_asset_document(
            conn,
            page_id=pdf_page_id,
            url=pdf_url,
            content_type="application/pdf",
            body=b"%PDF-1.4 broken-but-good-enough-for-test",
        )
        store_resource_link(
            conn,
            source_url=page_url,
            target_url=pdf_url,
            normalized_target_url=pdf_url,
            link_text="Methodological PDF",
            section_heading="Base and reference rates",
            resource_kind="asset_document",
            embed_type="item",
        )

        dataset_id = store_isaweb_dataset(
            conn,
            hierid=321,
            lang="EN",
            pos=["VDBFKBSC217000"],
            dimensions={"dval1": ["AT"]},
            freq="M",
            title="Base rates",
            source_url="https://www.oenb.at/isadataservice/data?lang=EN&hierid=321&pos=VDBFKBSC217000&dval1=AT&freq=M",
        )
        store_isaweb_observations(
            conn,
            dataset_id=dataset_id,
            observations=[
                {"period": "2026-01", "value": "2.50", "unit": "%", "series_label": "Base rates"},
                {"period": "2026-02", "value": "2.75", "unit": "%", "series_label": "Base rates"},
            ],
        )
        store_isaweb_page_context(
            conn,
            source_url=page_url,
            target_url="https://www.oenb.at/isawebstat/stabfrage/createReport?report=3.21.1&lang=EN",
            link_text="Base rates",
            section_heading="Base and reference rates",
            relation_kind="isaweb_entry",
        )
        store_isaweb_meta_response(
            conn,
            response_url="https://www.oenb.at/isadataservice/meta?lang=EN&hierid=321&pos=VDBFKBSC217000",
            xml_text="""<?xml version="1.0" encoding="UTF-8"?>
            <metainfo>
              <meta>
                <title>Base rates</title>
                <comment>Policy rates overview.</comment>
                <source>OeNB, ECB</source>
              </meta>
            </metainfo>
            """,
        )

        export_knowledge_base_jsonl(db_path, output_path)

        lines = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
        family_chunk = next(
            line for line in lines
            if line["record_type"] == "chatbot_chunk" and line["chunk_kind"] == "family_summary"
        )
        isaweb_chunk = next(
            line for line in lines
            if line["record_type"] == "chatbot_chunk" and line["chunk_kind"] == "isaweb_dataset_summary"
        )
        csv_chunk = next(
            line for line in lines
            if line["record_type"] == "chatbot_chunk"
            and line["chunk_kind"] == "asset_document_summary"
            and line["title"] == "Download CSV"
        )
        pdf_chunk = next(
            line for line in lines
            if line["record_type"] == "chatbot_chunk"
            and line["chunk_kind"] == "asset_document_summary"
            and line["title"] == "Methodological PDF"
        )

        assert family_chunk["retrieval_score"] > isaweb_chunk["retrieval_score"]
        assert isaweb_chunk["retrieval_score"] > csv_chunk["retrieval_score"]
        assert csv_chunk["retrieval_score"] > pdf_chunk["retrieval_score"]
        assert family_chunk["retrieval_tier"] == "primary"
        assert isaweb_chunk["retrieval_tier"] == "primary"
        assert csv_chunk["retrieval_tier"] == "secondary"
        assert pdf_chunk["retrieval_tier"] == "background"


def test_latest_observation_prefers_latest_date_like_period():
    latest = _latest_observation(
        [
            {"period": "31.08.01", "value": "5.50", "unit": "% per annum", "series_label": "Reference rate"},
            {"period": "22.03.23", "value": "4.00", "unit": "% per annum", "series_label": "Reference rate"},
            {"period": "27.07.22", "value": "x", "unit": "% per annum", "series_label": "Reference rate"},
        ]
    )

    assert latest == {
        "period": "22.03.23",
        "value": "4.00",
        "unit": "% per annum",
        "series_label": "Reference rate",
    }


def test_latest_observation_prefers_latest_quarter():
    latest = _latest_observation(
        [
            {"period": "Q4 24", "value": "21.93", "unit": "in %", "series_label": "FSI"},
            {"period": "Q3 25", "value": "26.63", "unit": "in %", "series_label": "FSI"},
            {"period": "Q1 25", "value": "22.15", "unit": "in %", "series_label": "FSI"},
        ]
    )

    assert latest == {
        "period": "Q3 25",
        "value": "26.63",
        "unit": "in %",
        "series_label": "FSI",
    }


def test_dataset_family_prefers_more_specific_statistics_page_as_primary_source():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "pages.db"
        output_path = Path(tmpdir) / "knowledge_base.jsonl"
        conn = init_db(db_path)
        run_id = start_crawl_run(conn, "https://www.oenb.at/", "TestBot/1.0")

        commodity_url = "https://www.oenb.at/en/Statistics/Standardized-Tables/Prices--Competitiveness/Commodity-Prices.html"
        rppi_url = (
            "https://www.oenb.at/en/Statistics/Standardized-Tables/Prices--Competitiveness/real-estate/"
            "residential-property-price-index.html"
        )

        commodity_page_id = store_page(
            conn,
            run_id=run_id,
            url=commodity_url,
            final_url=commodity_url,
            status_code=200,
            content_type="text/html",
            body=b"<html><body>Commodity prices</body></html>",
        )
        conn.execute(
            """
            INSERT INTO page_content (page_id, title, text_content, page_section, language, extracted_at, extractor_version)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                commodity_page_id,
                "Commodity prices",
                "Commodity prices overview.",
                "Statistics",
                "en",
                "2026-03-19T10:00:00Z",
                "page-extractor-v1",
            ),
        )

        chart_url = "https://www.oenb.at/isawebstat/createChart?lang=EN&report=6.6"
        chart_page_id = store_page(
            conn,
            run_id=run_id,
            url=chart_url,
            final_url=chart_url,
            status_code=200,
            content_type="text/html",
            body=b"<html><body>DATA Chart - Selected inflation indicators</body></html>",
        )
        conn.execute(
            """
            INSERT INTO page_content (page_id, title, text_content, page_section, language, extracted_at, extractor_version)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chart_page_id,
                "DATA Chart - Selected inflation indicators",
                "Selected inflation indicators chart page.",
                "Statistics",
                "en",
                "2026-03-19T10:01:30Z",
                "page-extractor-v1",
            ),
        )
        unrelated_chart_url = "https://www.oenb.at/isawebstat/createChart?lang=EN&report=6.1"
        unrelated_chart_page_id = store_page(
            conn,
            run_id=run_id,
            url=unrelated_chart_url,
            final_url=unrelated_chart_url,
            status_code=200,
            content_type="text/html",
            body=b"<html><body>DATA Chart - Selected inflation indicators</body></html>",
        )
        conn.execute(
            """
            INSERT INTO page_content (page_id, title, text_content, page_section, language, extracted_at, extractor_version)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                unrelated_chart_page_id,
                "DATA Chart - Selected inflation indicators",
                "Selected inflation indicators chart page.",
                "Statistics",
                "en",
                "2026-03-19T10:01:45Z",
                "page-extractor-v1",
            ),
        )

        rppi_page_id = store_page(
            conn,
            run_id=run_id,
            url=rppi_url,
            final_url=rppi_url,
            status_code=200,
            content_type="text/html",
            body=b"<html><body>Residential property price index</body></html>",
        )
        conn.execute(
            """
            INSERT INTO page_content (page_id, title, text_content, page_section, language, extracted_at, extractor_version)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rppi_page_id,
                "Residential property price index",
                "Residential property price index detail page.",
                "Statistics",
                "en",
                "2026-03-19T10:01:00Z",
                "page-extractor-v1",
            ),
        )

        dataset_id = store_isaweb_dataset(
            conn,
            hierid=6,
            lang="EN",
            pos=["VDBPLIMOPAT00"],
            dimensions={"dval1": ["N"], "dval2": ["AT"], "dval3": ["Z5"], "dval4": ["01"]},
            freq="Q",
            title="Real estate price index, Austria (excl. Vienna), 2000=100",
            source_url="https://www.oenb.at/isadataservice/data?hierid=6&lang=EN&pos=VDBPLIMOPAT00",
        )
        store_isaweb_observations(
            conn,
            dataset_id=dataset_id,
            observations=[
                {
                    "period": "2024",
                    "value": "256.1",
                    "unit": "Index",
                    "series_label": "Real estate price index, Austria (excl. Vienna), 2000=100",
                },
                {
                    "period": "2025",
                    "value": "257.8",
                    "unit": "Index",
                    "series_label": "Real estate price index, Austria (excl. Vienna), 2000=100",
                },
            ],
        )
        store_isaweb_page_context(
            conn,
            source_url=commodity_url,
            target_url="https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=6.6",
            link_text="Residential property price index",
            section_heading="Real estate",
            relation_kind="isaweb_entry",
        )
        store_isaweb_page_context(
            conn,
            source_url=rppi_url,
            target_url="https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=6.6",
            link_text="Residential property price index",
            section_heading="Real estate",
            relation_kind="isaweb_entry",
        )
        store_isaweb_page_context(
            conn,
            source_url=chart_url,
            target_url="https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=6.6",
            link_text="Chart",
            section_heading="Prices, competitiveness",
            relation_kind="isaweb_entry",
        )
        store_isaweb_page_context(
            conn,
            source_url=unrelated_chart_url,
            target_url="https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=6.1",
            link_text="Chart",
            section_heading="Prices, competitiveness",
            relation_kind="isaweb_entry",
        )
        store_isaweb_meta_response(
            conn,
            response_url="https://www.oenb.at/isadataservice/meta?lang=EN&hierid=6&pos=VDBPLIMOPAT00",
            xml_text="""<?xml version="1.0" encoding="UTF-8"?>
            <metainfo>
              <meta>
                <title>Real estate price index, Austria (excl. Vienna), 2000=100</title>
                <comment>Residential property price index metadata.</comment>
                <frequency>quarterly</frequency>
                <source>OeNB, DataScience Service GmbH (DSS)</source>
              </meta>
            </metainfo>
            """,
        )

        export_knowledge_base_jsonl(db_path, output_path)

        family_record = next(
            line
            for line in map(json.loads, output_path.read_text(encoding="utf-8").splitlines())
            if line["record_type"] == "dataset_family"
        )

        assert family_record["source_page"]["url"] == rppi_url
        assert family_record["source_page"]["title"] == "Residential property price index"


def test_dataset_family_prefers_statistics_page_over_unrelated_isaweb_chart_from_same_hierarchy():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "pages.db"
        output_path = Path(tmpdir) / "knowledge_base.jsonl"
        conn = init_db(db_path)
        run_id = start_crawl_run(conn, "https://www.oenb.at/", "TestBot/1.0")

        real_estate_url = "https://www.oenb.at/en/Statistics/Standardized-Tables/Prices--Competitiveness/real-estate.html"
        rppi_url = (
            "https://www.oenb.at/en/Statistics/Standardized-Tables/Prices--Competitiveness/real-estate/"
            "residential-property-price-index.html"
        )
        unrelated_chart_url = "https://www.oenb.at/isawebstat/createChart?lang=EN&report=6.1"

        for url, title, text in [
            (real_estate_url, "Real estate", "Real estate overview with Residential property price index."),
            (rppi_url, "Residential property price index", "Residential property price index detail page."),
            (unrelated_chart_url, "DATA Chart - Selected inflation indicators", "Selected inflation indicators chart."),
        ]:
            page_id = store_page(
                conn,
                run_id=run_id,
                url=url,
                final_url=url,
                status_code=200,
                content_type="text/html",
                body=f"<html><body>{title}</body></html>".encode("utf-8"),
            )
            conn.execute(
                """
                INSERT INTO page_content (page_id, title, text_content, page_section, language, extracted_at, extractor_version)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    page_id,
                    title,
                    text,
                    "Statistics",
                    "en",
                    "2026-03-19T10:00:00Z",
                    "page-extractor-v1",
                ),
            )

        dataset_id = store_isaweb_dataset(
            conn,
            hierid=6,
            lang="EN",
            pos=["VDBPLIMOPATGEZBN"],
            dimensions={"dval1": ["N"], "dval2": ["AT"], "dval3": ["Z5"], "dval4": ["01"]},
            freq="Q",
            title="Austria - Residential Property Price Index 2000=100 hedonic regr model",
            source_url="https://www.oenb.at/isadataservice/data?hierid=6&lang=EN&pos=VDBPLIMOPATGEZBN",
        )
        store_isaweb_observations(
            conn,
            dataset_id=dataset_id,
            observations=[
                {
                    "period": "2025-Q1",
                    "value": "257.8",
                    "unit": "Index",
                    "series_label": "Austria - Residential Property Price Index 2000=100 hedonic regr model",
                }
            ],
        )

        store_isaweb_page_context(
            conn,
            source_url=real_estate_url,
            target_url="https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=6.6",
            link_text="Table",
            section_heading="Real estate",
            relation_kind="isaweb_entry",
        )
        store_isaweb_page_context(
            conn,
            source_url=unrelated_chart_url,
            target_url="https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=6.1",
            link_text="Chart",
            section_heading="Prices, competitiveness",
            relation_kind="isaweb_entry",
        )

        export_knowledge_base_jsonl(db_path, output_path)

        family_record = next(
            line
            for line in map(json.loads, output_path.read_text(encoding="utf-8").splitlines())
            if line["record_type"] == "dataset_family"
        )

        assert family_record["source_page"]["url"] == rppi_url
        assert family_record["source_page"]["title"] == "Residential property price index"


def test_dataset_family_sources_do_not_pull_unrelated_supporting_page_sources():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "pages.db"
        output_path = Path(tmpdir) / "knowledge_base.jsonl"
        conn = init_db(db_path)
        run_id = start_crawl_run(conn, "https://www.oenb.at/", "TestBot/1.0")

        primary_url = "https://www.oenb.at/en/Statistics/Standardized-Tables/Interest-rates/Base-and-reference-rates.html"
        supporting_url = "https://www.oenb.at/en/Statistics/Standardized-Tables/Interest-rates/noisy-context.html"

        for url, title, text in [
            (primary_url, "Base and reference rates", "Source: OeNB, ECB. Main statistics page."),
            (supporting_url, "Noisy context", "Source: Federal Ministry of Finance, Statistics Austria. Unrelated context page."),
        ]:
            page_id = store_page(
                conn,
                run_id=run_id,
                url=url,
                final_url=url,
                status_code=200,
                content_type="text/html",
                body=f"<html><body>{title}</body></html>".encode("utf-8"),
            )
            conn.execute(
                """
                INSERT INTO page_content (page_id, title, text_content, page_section, language, extracted_at, extractor_version)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    page_id,
                    title,
                    text,
                    "Statistics",
                    "en",
                    "2026-03-19T10:00:00Z",
                    "page-extractor-v1",
                ),
            )

        store_resource_link(
            conn,
            source_url=primary_url,
            target_url=supporting_url,
            normalized_target_url=supporting_url,
            link_text="Context",
            section_heading="Interest rates",
            resource_kind="page_document",
            embed_type="item",
        )

        dataset_id = store_isaweb_dataset(
            conn,
            hierid=2,
            lang="EN",
            pos=["REPORT:2.1"],
            dimensions={"report_id": ["2.1"]},
            title="Base and Reference Rates of the Oesterreichische Nationalbank",
            source_url="https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=2.1",
        )
        store_isaweb_observations(
            conn,
            dataset_id=dataset_id,
            observations=[
                {"period": "11.06.25", "value": "1.53", "unit": "% per annum", "series_label": "Base rate"},
            ],
        )
        store_isaweb_page_context(
            conn,
            source_url=primary_url,
            target_url="https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=2.1",
            link_text="Base and reference rates",
            section_heading="Interest rates",
            relation_kind="isaweb_entry",
        )
        store_isaweb_meta_response(
            conn,
            response_url="https://www.oenb.at/isadataservice/meta?lang=EN&hierid=2&pos=REPORT:2.1",
            xml_text="""<?xml version="1.0" encoding="UTF-8"?>
            <metainfo>
              <meta>
                <title>Base and Reference Rates of the Oesterreichische Nationalbank</title>
                <source>OeNB, ECB</source>
              </meta>
            </metainfo>
            """,
        )

        export_knowledge_base_jsonl(db_path, output_path)

        family_record = next(
            line
            for line in map(json.loads, output_path.read_text(encoding="utf-8").splitlines())
            if line["record_type"] == "dataset_family"
        )

        assert "OeNB" in family_record["sources"]
        assert "ECB" in family_record["sources"]
        assert "Federal Ministry of Finance" not in family_record["sources"]


def test_dataset_family_includes_release_events_from_matching_metadata_title_for_report_dataset():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "pages.db"
        output_path = Path(tmpdir) / "knowledge_base.jsonl"
        conn = init_db(db_path)
        run_id = start_crawl_run(conn, "https://www.oenb.at/", "TestBot/1.0")

        primary_url = (
            "https://www.oenb.at/en/Statistics/Standardized-Tables/Financial-Institutions/banks/"
            "aggregated-regulatory-capital-requirements-and-liquidity-financial-and-income-statements/"
            "financial-soundness-indicators-acc.-imf.html"
        )
        page_id = store_page(
            conn,
            run_id=run_id,
            url=primary_url,
            final_url=primary_url,
            status_code=200,
            content_type="text/html",
            body=b"<html><body>Financial Soundness Indicators</body></html>",
        )
        conn.execute(
            """
            INSERT INTO page_content (page_id, title, text_content, page_section, language, extracted_at, extractor_version)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                page_id,
                "Financial Soundness Indicators",
                "Statistics page for financial soundness indicators.",
                "Statistics",
                "en",
                "2026-03-19T10:00:00Z",
                "page-extractor-v1",
            ),
        )

        dataset_id = store_isaweb_dataset(
            conn,
            hierid=324,
            lang="EN",
            pos=["REPORT:3.24.15"],
            dimensions={"report_id": ["3.24.15"]},
            freq="Q",
            title="Financial Soundness Indicators",
            source_url="https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=3.24.15",
        )
        store_isaweb_observations(
            conn,
            dataset_id=dataset_id,
            observations=[
                {"period": "Q3 25", "value": "19.52", "unit": "in %", "series_label": "Regulatory Tier 1 capital to risk-weighted assets"},
            ],
        )
        store_isaweb_page_context(
            conn,
            source_url=primary_url,
            target_url="https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=3.24.15",
            link_text="Financial Soundness Indicators",
            section_heading="Banks",
            relation_kind="isaweb_entry",
        )
        store_isaweb_meta_response(
            conn,
            response_url="https://www.oenb.at/isadataservice/meta?hierid=324&lang=EN&pos=VDBKIFSI01",
            xml_text="""<?xml version="1.0" encoding="UTF-8"?>
            <metainfo>
              <meta>
                <title>Financial Soundness Indicators</title>
                <source>OeNB</source>
                <releases>
                  <release><release_date>at the latest 31.03.2026</release_date><reference>4. Quarter 2025</reference><revision></revision></release>
                </releases>
              </meta>
            </metainfo>
            """,
        )

        export_knowledge_base_jsonl(db_path, output_path)

        family_record = next(
            line
            for line in map(json.loads, output_path.read_text(encoding="utf-8").splitlines())
            if line["record_type"] == "dataset_family"
        )

        assert len(family_record["release_events"]) == 1
        release = family_record["release_events"][0]
        assert release["hierid"] == 324
        assert release["lang"] == "EN"
        assert release["pos"] == "VDBKIFSI01"
        assert release["release_date_text"] == "at the latest 31.03.2026"
        assert release["reference_text"] == "4. Quarter 2025"
        assert release["revision_text"] in {"", None}
        assert release["source_url"] == "https://www.oenb.at/isadataservice/meta?hierid=324&lang=EN&pos=VDBKIFSI01"


def test_build_family_chunk_text_limits_supporting_pages():
    text = _build_family_chunk_text(
        {
            "title": "Financial Soundness Indicators",
            "source_page": {
                "title": "Financial Soundness Indicators acc. IMF - Oesterreichische Nationalbank (OeNB)",
            },
            "latest_observation": {
                "period": "Q3 25",
                "value": "19.52",
                "unit": "in %",
            },
            "sources": ["OeNB", "IMF"],
            "supporting_pages": [
                {"title": "Page 1"},
                {"title": "Page 2"},
                {"title": "Page 3"},
                {"title": "Page 4"},
                {"title": "Page 5"},
                {"title": "Page 6"},
            ],
        }
    )

    assert "Supporting pages: Page 1, Page 2, Page 3, Page 4, Page 5, +1 more." in text
    assert "Page 6" not in text


def test_latest_observations_by_series_keeps_multiple_current_columns():
    rows = [
        {"period": "11.06.25", "value": "1.53", "unit": "% per annum", "series_label": "Base rate"},
        {"period": "11.06.25", "value": "2.65", "unit": "% per annum", "series_label": "Reference rate"},
        {"period": "12.03.25", "value": "2.03", "unit": "% per annum", "series_label": "Base rate"},
        {"period": "12.03.25", "value": "3.15", "unit": "% per annum", "series_label": "Reference rate"},
    ]

    latest_rows = _latest_observations_by_series(rows)

    assert latest_rows == [
        {
            "period": "11.06.25",
            "value": "1.53",
            "unit": "% per annum",
            "series_label": "Base rate",
        },
        {
            "period": "11.06.25",
            "value": "2.65",
            "unit": "% per annum",
            "series_label": "Reference rate",
        },
    ]
