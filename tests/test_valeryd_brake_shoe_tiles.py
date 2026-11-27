import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location(
    "valeryd_brake_shoe_tiles",
    pathlib.Path(__file__).resolve().parents[1] / "scripts/aftermarket_pdf/valeryd_brake_shoe_tiles.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_caption_with_two_fit_lines():
    r, why = m.parse_caption(["Art.Nr.: 4010001A", "KNOTT 16-1365 Neue Ausf. (ab Bj. -89)", "BPW S1635-6 RASK",
                              "Storlek: 160x35"])
    assert why is None
    assert r == {"number": "4010001A", "fits": "KNOTT 16-1365 Neue Ausf. (ab Bj. -89) BPW S1635-6 RASK",
                 "size": "160x35"}


def test_superkit_badge_and_upper_case_size():
    r, _ = m.parse_caption(["Art.Nr.: 5010206XL SUPERKIT", "AL-KO 2360, 2361", "Storlek: 230X60"])
    assert r["number"] == "5010206XL" and r["size"] == "230x60"


def test_band_set_without_suffix():
    r, _ = m.parse_caption(["Art.Nr.: 4010009", "Bromsbandset", "Storlek: 230x40"])
    assert r["number"] == "4010009" and r["fits"] == "Bromsbandset"


def test_rejects_glued_or_missing_parts():
    assert m.parse_caption(["Art.Nr.: 4010210A Art.Nr.:", "Storlek: 200x50"])[0] is None
    assert m.parse_caption(["Art.Nr.: 4010201A", "AL-KO 1637"])[0] is None
    assert m.parse_caption(["AL-KO 1637", "Storlek: 160x35"])[0] is None
