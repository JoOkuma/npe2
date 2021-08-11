from enum import Enum
from pathlib import Path
from typing import Callable, List, Optional

from pydantic import BaseModel, Field

from .contributions import ContributionPoints

spdx_ids = (Path(__file__).parent / "spdx.txt").read_text().splitlines()
SPDX = Enum("SPDX", {i.replace("-", "_"): i for i in spdx_ids})  # type: ignore


class PluginManifest(BaseModel):
    # VS Code uses <publisher>.<name> as a unique ID for the extension
    name: str = Field(
        ...,
        description="The name of the plugin - should be all lowercase with no spaces.",
    )
    publisher: str = Field(
        "unidentified_publisher",
        description="The publisher name - can be an individual or an organization",
    )
    entry_point: Path = Field(..., description="The extension entry point.")
    version: Optional[str] = Field(None, description="SemVer compatible version.")
    contributes: Optional[ContributionPoints]
    license: Optional[SPDX] = None
    description: Optional[str] = Field(
        description="A short description of what your extension is and does."
    )
    manifest_file: Optional[Path]
    display_name: str = Field(
        "",
        description="The display name for the extension used in the Marketplace.",
    )
    keywords: List[str] = Field(
        default_factory=list,
        description="An array of keywords to make it easier to find the "
        "extension. These are included with other extension Tags on the "
        "Marketplace. This list is currently limited to 5 keywords",
    )
    preview: bool = Field(
        False,
        description="Sets the extension to be flagged as a Preview in napari-hub.",
    )

    # activationEvents: Optional[List[ActivationEvent]] = Field(
    #     default_factory=list,
    #     description="Events upon which your extension becomes active.",
    # )

    # @validator("activationEvents", pre=True)
    # def _validateActivationEvent(cls, val):
    #     return [
    #         dict(zip(("kind", "id"), x.split(":"))) if ":" in x else x
    #         for x in val
    #     ]

    @classmethod
    def from_pyproject(cls, path):
        import toml

        data = toml.load(path)
        return cls(**data["tool"]["napari"], manifest_file=path)

    def toml(self):
        import toml

        return toml.dumps({"tool": {"napari": self.dict(exclude_unset=True)}})

    def yaml(self):
        import yaml
        import json

        return yaml.safe_dump(json.loads(self.json(exclude_unset=True)))

    @classmethod
    def from_file(cls, path) -> "PluginManifest":
        loader: Callable
        if str(path).lower().endswith(".json"):
            import json

            loader = json.load
        elif str(path).lower().endswith(".toml"):
            import toml

            loader = toml.load
        elif str(path).lower().endswith((".yaml", ".yml")):
            import yaml

            loader = yaml.safe_load
        else:
            raise ValueError(f"unrecognized file extension: {path}")
        with open(path) as f:
            data = loader(f) or {}
            return cls(**data)

    class Config:
        use_enum_values = True  # only needed for SPDX

    # should these be on this model itself? or helper functions elsewhere

    @property
    def _root(self):
        if self.manifest_file:
            return self.manifest_file.parent
        return Path(".")

    def import_entry_point(self):
        import sys
        from importlib import util

        mod_name = f"{self.name}.{self.entry_point.stem}"
        if mod_name in sys.modules:
            return sys.modules[mod_name]

        ep = self._root / self.entry_point
        spec = util.spec_from_file_location(mod_name, str(ep.absolute()))
        if not spec:
            raise ImportError(f"No ModuleSpec for module {mod_name}")
        module = util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
        return module

    def activate(self):
        mod = self.import_entry_point()
        activate = getattr(mod, "activate")
        activate()

    @classmethod
    def discover(cls) -> List["PluginManifest"]:
        """Discover manifests in the environment."""
        from importlib.metadata import entry_points
        import sys

        manifests = []
        for ep in entry_points().get("napari.manifest", []):
            for finder in sys.meta_path:
                spec = finder.find_spec(ep.module, None)
                if not (spec and spec.submodule_search_locations):
                    continue
                for loc in spec.submodule_search_locations:
                    manifest = Path(loc) / ep.attr
                    if manifest.exists():
                        manifests.append(PluginManifest.from_file(manifest))
                        break
            else:
                import warnings

                warnings.warn(
                    "A napari.manifest entry_point was declared, "
                    f"but the target could not be imported: {ep}"
                )
        return manifests


if __name__ == "__main__":
    print(PluginManifest.schema_json())
