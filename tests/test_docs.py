"""The documents must agree with the data and with each other. Offline."""
import html
import json
import pathlib
import re
import tomllib

import pytest

ROOT = pathlib.Path(__file__).parent.parent
DOCS = ROOT / "docs"
RESULTS = json.loads((DOCS / "data" / "results.json").read_text())
README = (ROOT / "README.md").read_text()
PAGES = ["index.html", "demo.html"]


def local(target):
    return not re.match(r"(https?:|mailto:|#|data:)", target)


@pytest.mark.parametrize("document", ["README.md", "CAVEATS.md", "docs/METHODOLOGY.md",
                                      "docs/RESULTS.md", "docs/LICENSE.md"])
def test_relative_links_of_markdown_resolve(document):
    path = ROOT / document
    text = path.read_text()
    targets = re.findall(r"\]\(([^)\s]+)\)", text) + re.findall(r'(?:src|href)="([^"]+)"', text)
    for target in filter(local, targets):
        assert (path.parent / target.split("#")[0]).exists(), f"{document}: {target}"


@pytest.mark.parametrize("page", PAGES)
def test_pages_load_only_files_that_exist(page):
    text = (DOCS / page).read_text()
    for target in filter(local, re.findall(r'(?:src|href|data-svg)="([^"]+)"', text)):
        assert (DOCS / target.split("#")[0].split("?")[0]).exists(), f"{page}: {target}"


def test_no_placeholder_survives_the_build():
    assert "${" not in (DOCS / "index.html").read_text()


def test_the_code_slide_shows_the_script():
    page = (DOCS / "index.html").read_text()
    block = re.search(r"<pre[^>]*><code>(.*?)</code></pre>", page, flags=re.S).group(1)
    lines = [html.unescape(re.sub(r"<[^>]+>", "", line))
             for line in re.findall(r'<span class="l">(.*?)</span>(?=<span class="l">|$)',
                                    block, flags=re.S)]
    assert "\n".join(lines).strip() == (ROOT / "dna.py").read_text().strip()


def test_readme_quotes_the_summary_of_the_run():
    blend = next(row for row in RESULTS["providers"] if row["provider"] == "meta")
    for row in RESULTS["summary"]:
        city = row["city"]
        quoted = f"| {row['cells']} | {row['flagged']} | Meta {blend[city]:.1f}% |"
        assert quoted in README, f"{city}: README should contain {quoted}"
    assert f"Overture-{RESULTS['meta']['release'].replace('-', '--')}" in README


def test_readme_quotes_the_districts():
    for row in RESULTS["districts"]:
        quoted = f"| {row['places']:,} | {row['hill_q2']:.2f} |"
        assert quoted in README, f"{row['district']}: README should contain {quoted}"


def test_versions_agree():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    citation = (ROOT / "CITATION.cff").read_text()
    assert f"\nversion: {project['version']}\n" in citation
    for pin in project["dependencies"]:
        assert pin in (ROOT / "requirements.txt").read_text()
        assert pin in (ROOT / "dna.py").read_text(), f"{pin} is missing from the script header"
