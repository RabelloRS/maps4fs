"""This module contains Map class, which is used to generate map using all components."""

from __future__ import annotations

import json
import os
import shutil
from typing import Any, Generator

from pydantic import BaseModel

from maps4fs.generator.component import Component
from maps4fs.generator.game import Game
from maps4fs.logger import Logger


class SettingsModel(BaseModel):
    """Base class for settings models. It provides methods to convert settings to and from JSON."""

    @classmethod
    def all_settings_to_json(cls) -> dict[str, dict[str, Any]]:
        """Get all settings of the current class and its subclasses as a dictionary.

        Returns:
            dict[str, dict[str, Any]]: Dictionary with settings of the current class and its
                subclasses.
        """
        all_settings = {}
        for subclass in cls.__subclasses__():
            all_settings[subclass.__name__] = subclass().model_dump()

        return all_settings

    @classmethod
    def all_settings_from_json(cls, data: dict) -> dict[str, SettingsModel]:
        """Create settings instances from JSON data.

        Arguments:
            data (dict): JSON data.

        Returns:
            dict[str, Type[SettingsModel]]: Dictionary with settings instances.
        """
        settings = {}
        for subclass in cls.__subclasses__():
            settings[subclass.__name__] = subclass(**data[subclass.__name__])

        return settings


class DEMSettings(SettingsModel):
    """Represents the advanced settings for DEM component.

    Attributes:
        auto_process (bool): use the auto preset to change the multiplier.
        multiplier (int): multiplier for the heightmap, every pixel will be multiplied by this
            value.
        blur_radius (int): radius of the blur filter.
        plateau (int): plateau height, will be added to each pixel.
        water_depth (int): water depth, will be subtracted from each pixel where the water
            is present.
    """

    auto_process: bool = True
    multiplier: int = 1
    blur_radius: int = 35
    plateau: int = 0
    water_depth: int = 0


class BackgroundSettings(SettingsModel):
    """Represents the advanced settings for background component.

    Attributes:
        generate_background (bool): generate obj files for the background terrain.
        generate_water (bool): generate obj files for the water.
        resize_factor (int): resize factor for the background terrain and water.
            It will be used as 1 / resize_factor of the original size.
    """

    generate_background: bool = True
    generate_water: bool = True
    resize_factor: int = 8


class GRLESettings(SettingsModel):
    """Represents the advanced settings for GRLE component.

    Attributes:
        farmland_margin (int): margin around the farmland.
        random_plants (bool): generate random plants on the map or use the default one.
        add_farmyards (bool): If True, regions of frarmyards will be added to the map
            without corresponding fields.
    """

    farmland_margin: int = 0
    random_plants: bool = True
    add_farmyards: bool = False


class I3DSettings(SettingsModel):
    """Represents the advanced settings for I3D component.

    Attributes:
        forest_density (int): density of the forest (distance between trees).
    """

    forest_density: int = 10


class TextureSettings(SettingsModel):
    """Represents the advanced settings for texture component.

    Attributes:
        dissolve (bool): dissolve the texture into several images.
        fields_padding (int): padding around the fields.
        skip_drains (bool): skip drains generation.
    """

    dissolve: bool = True
    fields_padding: int = 0
    skip_drains: bool = False


class SplineSettings(SettingsModel):
    """Represents the advanced settings for spline component.

    Attributes:
        spline_density (int): the number of extra points that will be added between each two
            existing points.
    """

    spline_density: int = 2


# pylint: disable=R0913, R0902, R0914
class Map:
    """Class used to generate map using all components.

    Arguments:
        game (Type[Game]): Game for which the map is generated.
        coordinates (tuple[float, float]): Coordinates of the center of the map.
        size (int): Height and width of the map in pixels (it's a square).
        map_directory (str): Path to the directory where map files will be stored.
        logger (Any): Logger instance
    """

    def __init__(  # pylint: disable=R0917, R0915
        self,
        game: Game,
        coordinates: tuple[float, float],
        size: int,
        rotation: int,
        map_directory: str,
        logger: Any = None,
        custom_osm: str | None = None,
        dem_settings: DEMSettings = DEMSettings(),
        background_settings: BackgroundSettings = BackgroundSettings(),
        grle_settings: GRLESettings = GRLESettings(),
        i3d_settings: I3DSettings = I3DSettings(),
        texture_settings: TextureSettings = TextureSettings(),
        spline_settings: SplineSettings = SplineSettings(),
        **kwargs,
    ):
        if not logger:
            logger = Logger(to_stdout=True, to_file=False)
        self.logger = logger
        self.size = size

        if rotation:
            rotation_multiplier = 1.5
        else:
            rotation_multiplier = 1

        self.rotation = rotation
        self.rotated_size = int(size * rotation_multiplier)

        self.game = game
        self.components: list[Component] = []
        self.coordinates = coordinates
        self.map_directory = map_directory

        self.logger.info("Game was set to %s", game.code)

        self.custom_osm = custom_osm
        self.logger.info("Custom OSM file: %s", custom_osm)

        # Make a copy of a custom osm file to the map directory, so it will be
        # included in the output archive.
        if custom_osm:
            copy_path = os.path.join(self.map_directory, "custom_osm.osm")
            shutil.copyfile(custom_osm, copy_path)
            self.logger.debug("Custom OSM file copied to %s", copy_path)

        self.dem_settings = dem_settings
        self.logger.info("DEM settings: %s", dem_settings)
        self.background_settings = background_settings
        self.logger.info("Background settings: %s", background_settings)
        self.grle_settings = grle_settings
        self.logger.info("GRLE settings: %s", grle_settings)
        self.i3d_settings = i3d_settings
        self.logger.info("I3D settings: %s", i3d_settings)
        self.texture_settings = texture_settings
        self.logger.info("Texture settings: %s", texture_settings)
        self.spline_settings = spline_settings
        self.logger.info("Spline settings: %s", spline_settings)

        os.makedirs(self.map_directory, exist_ok=True)
        self.logger.debug("Map directory created: %s", self.map_directory)

        self.texture_custom_schema = kwargs.get("texture_custom_schema", None)
        if self.texture_custom_schema:
            save_path = os.path.join(self.map_directory, "texture_custom_schema.json")
            with open(save_path, "w", encoding="utf-8") as file:
                json.dump(self.texture_custom_schema, file, indent=4)
            self.logger.debug("Texture custom schema saved to %s", save_path)

        self.tree_custom_schema = kwargs.get("tree_custom_schema", None)
        if self.tree_custom_schema:
            save_path = os.path.join(self.map_directory, "tree_custom_schema.json")
            with open(save_path, "w", encoding="utf-8") as file:
                json.dump(self.tree_custom_schema, file, indent=4)
            self.logger.debug("Tree custom schema saved to %s", save_path)

        try:
            shutil.unpack_archive(game.template_path, self.map_directory)
            self.logger.debug("Map template unpacked to %s", self.map_directory)
        except Exception as e:
            raise RuntimeError(f"Can not unpack map template due to error: {e}") from e

    def generate(self) -> Generator[str, None, None]:
        """Launch map generation using all components. Yield component names during the process.

        Yields:
            Generator[str, None, None]: Component names.
        """
        self.logger.info(
            "Starting map generation. Game code: %s. Coordinates: %s, size: %s. Rotation: %s.",
            self.game.code,
            self.coordinates,
            self.size,
            self.rotation,
        )

        for game_component in self.game.components:
            component = game_component(
                self.game,
                self,
                self.coordinates,
                self.size,
                self.rotated_size,
                self.rotation,
                self.map_directory,
                self.logger,
                texture_custom_schema=self.texture_custom_schema,
                tree_custom_schema=self.tree_custom_schema,
            )
            self.components.append(component)

            yield component.__class__.__name__

            try:
                component.process()
            except Exception as e:  # pylint: disable=W0718
                self.logger.error(
                    "Error processing component %s: %s",
                    component.__class__.__name__,
                    e,
                )
                raise e

            try:
                component.commit_generation_info()
            except Exception as e:  # pylint: disable=W0718
                self.logger.error(
                    "Error committing generation info for component %s: %s",
                    component.__class__.__name__,
                    e,
                )
                raise e

        self.logger.info(
            "Map generation completed. Game code: %s. Coordinates: %s, size: %s. Rotation: %s.",
            self.game.code,
            self.coordinates,
            self.size,
            self.rotation,
        )

    def get_component(self, component_name: str) -> Component | None:
        """Get component by name.

        Arguments:
            component_name (str): Name of the component.

        Returns:
            Component | None: Component instance or None if not found.
        """
        for component in self.components:
            if component.__class__.__name__ == component_name:
                return component
        return None

    def previews(self) -> list[str]:
        """Get list of preview images.

        Returns:
            list[str]: List of preview images.
        """
        previews = []
        for component in self.components:
            try:
                previews.extend(component.previews())
            except Exception as e:  # pylint: disable=W0718
                self.logger.error(
                    "Error getting previews for component %s: %s",
                    component.__class__.__name__,
                    e,
                )
        return previews

    def pack(self, archive_path: str, remove_source: bool = True) -> str:
        """Pack map directory to zip archive.

        Arguments:
            archive_path (str): Path to the archive.
            remove_source (bool, optional): Remove source directory after packing.

        Returns:
            str: Path to the archive.
        """
        archive_path = shutil.make_archive(archive_path, "zip", self.map_directory)
        self.logger.info("Map packed to %s.zip", archive_path)
        if remove_source:
            try:
                shutil.rmtree(self.map_directory)
                self.logger.debug("Map directory removed: %s", self.map_directory)
            except Exception as e:  # pylint: disable=W0718
                self.logger.debug("Error removing map directory %s: %s", self.map_directory, e)
        return archive_path
