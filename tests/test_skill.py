import os
import yaml

SKILL_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".agents", "skills", "manage-memory", "SKILL.md")

def test_skill_valid_metadata():
    with open(SKILL_PATH, encoding="utf-8") as f:
        content = f.read()
    assert content.startswith("---"), "SKILL.md debe comenzar con YAML frontmatter"
    parts = content.split("---", 2)
    assert len(parts) >= 3, "SKILL.md debe tener YAML frontmatter con cierre"
    meta = yaml.safe_load(parts[1])
    assert isinstance(meta, dict)
    assert "name" in meta
    assert "description" in meta
