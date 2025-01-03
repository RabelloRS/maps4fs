import json
import os
from datetime import datetime
from time import perf_counter

import config
import osmp
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image
from queuing import add_to_queue, remove_from_queue, wait_in_queue
from streamlit_stl import stl_from_file
from templates import Messages

import maps4fs as mfs

DEFAULT_MULTIPLIER = 1
DEFAULT_BLUR_RADIUS = 35
DEFAULT_PLATEAU = 0
DEFAULT_LAT = 45.28571409289627
DEFAULT_LON = 20.237433441210115
Image.MAX_IMAGE_PIXELS = None


class GeneratorUI:
    """Main class for the Maps4FS web interface.

    Attributes:
        download_path (str): The path to the generated map archive.
        logger (Logger): The logger instance.

    Properties:
        lat_lon (tuple[float, float]): The latitude and longitude of the center point of the map.
        map_size (tuple[int, int]): The size of the map in meters.

    Public methods:
        map_preview: Generate a preview of the map.
        add_right_widgets: Add widgets to the right column.
        add_left_widgets: Add widgets to the left column.
        generate_map: Generate the map.
        get_sesion_name: Generate a session name for the map.
        shorten_coordinate: Shorten a coordinate to a string.
        show_preview: Show the preview of the generated map.
    """

    def __init__(self):
        self.download_path = None
        self.logger = mfs.Logger(level="INFO", to_file=False)

        self.public = config.is_public()
        self.logger.debug("The application launched on a public server: %s", self.public)

        self.left_column, self.right_column = st.columns(2, gap="large")

        if "generated" not in st.session_state:
            st.session_state.generated = False

        with self.right_column:
            self.add_right_widgets()

        with self.left_column:
            if config.is_on_community_server():
                st.error(Messages.MOVED, icon="🚜")
            self.add_left_widgets()

        self.map_preview()

    @property
    def lat_lon(self) -> tuple[float, float]:
        """Get the latitude and longitude of the center point of the map.

        Returns:
            tuple[float, float]: The latitude and longitude of the center point of the map.
        """
        return tuple(map(float, self.lat_lon_input.split(",")))

    @property
    def map_size(self) -> tuple[int, int]:
        """Get the size of the map in meters.

        Returns:
            tuple[int, int]: The size of the map in meters.
        """
        return tuple(map(int, self.map_size_input.split("x")))

    def map_preview(self) -> None:
        """Generate a preview of the map in the HTML container.
        This method is called when the latitude, longitude, or map size is changed.
        """
        try:
            lat, lon = self.lat_lon
        except ValueError:
            return

        try:
            map_size, _ = self.map_size
        except ValueError:
            return

        self.logger.debug(
            "Generating map preview for lat=%s, lon=%s, map_size=%s", lat, lon, map_size
        )

        html_file = osmp.get_rotated_preview(lat, lon, map_size, angle=-self.rotation)

        with self.html_preview_container:
            components.html(open(html_file).read(), height=600)

    def add_right_widgets(self) -> None:
        """Add widgets to the right column."""
        self.logger.debug("Adding widgets to the right column...")
        self.html_preview_container = st.empty()
        self.map_selector_container = st.container()
        self.preview_container = st.container()

    def add_left_widgets(self) -> None:
        """Add widgets to the left column."""
        self.logger.debug("Adding widgets to the left column...")

        st.title(Messages.TITLE)

        # Only for a local Docker version.
        if not self.public:
            versions = config.get_versions(self.logger)
            try:
                if versions:
                    latest_version, current_version = versions
                    if current_version != latest_version and len(current_version) > 0:
                        st.warning(
                            f"🆕 New version is available!   \n"
                            f"Your current version: `{current_version}`, "
                            f"latest version: `{latest_version}`.   \n"
                            "Use the following commands to upgrade:   \n"
                            "```bash   \n"
                            "docker stop maps4fs   \n"
                            "docker rm maps4fs   \n"
                            "docker run -d -p 8501:8501 --name maps4fs "
                            f"iwatkot/maps4fs:{latest_version}   \n"
                            "```"
                        )
            except Exception as e:
                self.logger.error("An error occurred while checking the package version: %s", e)

        st.write(Messages.MAIN_PAGE_DESCRIPTION)
        st.markdown("---")

        # Game selection (FS22 or FS25).
        st.write("Select the game for which you want to generate the map:")
        self.game_code = st.selectbox(
            "Game",
            options=[
                "FS25",
                "FS22",
            ],
            key="game_code",
            label_visibility="collapsed",
        )

        # Latitude and longitude input.
        st.write("Enter latitude and longitude of the center point of the map:")
        self.lat_lon_input = st.text_input(
            "Latitude and Longitude",
            f"{DEFAULT_LAT}, {DEFAULT_LON}",
            key="lat_lon",
            label_visibility="collapsed",
            on_change=self.map_preview,
        )

        size_options = ["2048x2048", "4096x4096", "8192x8192", "16384x16384", "Custom"]
        if self.public:
            size_options = size_options[:3]

        # Map size selection.
        st.write("Select size of the map:")
        self.map_size_input = st.selectbox(
            "Map Size (meters)",
            options=size_options,
            label_visibility="collapsed",
            on_change=self.map_preview,
        )

        if self.map_size_input == "Custom":
            self.logger.debug("Custom map size selected.")

            st.info("ℹ️ Map size can be only a power of 2. For example: 2, 4, ... 2048, 4096, ...")
            st.warning("⚠️ Large map sizes can crash on generation or import in the game.")
            st.write("Enter map size (meters):")
            custom_map_size_input = st.number_input(
                label="Height (meters)",
                min_value=2,
                value=2048,
                key="map_height",
                label_visibility="collapsed",
                on_change=self.map_preview,
            )

            self.map_size_input = f"{custom_map_size_input}x{custom_map_size_input}"

        # Rotation input.
        st.write("Enter the rotation of the map:")

        self.rotation = st.slider(
            "Rotation",
            min_value=-180,
            max_value=180,
            value=0,
            step=1,
            key="rotation",
            label_visibility="collapsed",
            disabled=False,
            on_change=self.map_preview,
        )

        self.auto_process = st.checkbox("Use auto preset", value=True, key="auto_process")
        if self.auto_process:
            self.logger.debug("Auto preset is enabled.")
            st.info(Messages.AUTO_PRESET_INFO)

        self.multiplier_input = DEFAULT_MULTIPLIER
        self.blur_radius_input = DEFAULT_BLUR_RADIUS
        self.plateau_height_input = DEFAULT_PLATEAU
        self.fields_padding = 0
        self.farmland_margin = 3
        self.forest_density = 10
        self.randomize_plants = True
        self.water_depth = 200
        self.dissolving_enabled = True
        self.generate_background = True
        self.generate_water = True
        self.skip_drains = False
        self.spline_density = 4
        self.background_resize_factor = 8
        self.expert_mode = False
        self.raw_config = None
        self.add_farmyards = False

        if not self.auto_process:
            self.logger.info("Auto preset is disabled.")

            st.info(Messages.AUTO_PRESET_DISABLED)

        if not self.public:
            enable_debug = st.checkbox("Enable debug logs", key="debug_logs")
            if enable_debug:
                self.logger = mfs.Logger(level="DEBUG", to_file=False)
            else:
                self.logger = mfs.Logger(level="INFO", to_file=False)

        self.custom_osm_path = None
        self.custom_osm_enabled = st.checkbox(
            "Upload custom OSM file",
            value=False,
            key="custom_osm_enabled",
        )

        if self.custom_osm_enabled:
            st.info(Messages.CUSTOM_OSM_INFO)

            uploaded_file = st.file_uploader("Choose a file", type=["osm"])
            if uploaded_file is not None:
                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                self.custom_osm_path = os.path.join(
                    config.INPUT_DIRECTORY, f"custom_osm_{timestamp}.osm"
                )
                with open(self.custom_osm_path, "wb") as f:
                    f.write(uploaded_file.read())
                st.success(f"Custom OSM file uploaded: {uploaded_file.name}")

        self.advanced_settings = st.checkbox(
            "Show advanced settings",
            key="advanced_settings",
        )

        if self.advanced_settings:
            self.logger.debug("Advanced settings are enabled.")

            st.warning("⚠️ Changing these settings can lead to unexpected results.")

            self.expert_mode = st.checkbox("Expert mode", key="expert_mode")

            if self.expert_mode:
                st.info("ℹ️ In expert mode you can change the raw configuration of the generation.")

                settings_model = mfs.SettingsModel
                all_settings = settings_model.all_settings_to_json()

                self.raw_config = st.text_area(
                    "Raw configuration",
                    value=json.dumps(all_settings, indent=2),
                    height=600,
                    label_visibility="collapsed",
                )

            else:
                with st.expander("DEM Advanced Settings", icon="⛰️"):
                    st.info(
                        "ℹ️ Settings related to the Digital Elevation Model (elevation map). "
                        "This file is used to generate the terrain of the map (hills, valleys, etc.)."
                    )
                    # Show multiplier and blur radius inputs.
                    st.write(Messages.DEM_MULTIPLIER_INFO)

                    if self.auto_process:
                        st.info("When the auto preset is enabled, the multiplier is set to 1.")

                    self.multiplier_input = st.number_input(
                        "Multiplier",
                        value=DEFAULT_MULTIPLIER,
                        min_value=0,
                        max_value=10000,
                        step=1,
                        key="multiplier",
                        disabled=self.auto_process,
                    )

                    st.write(Messages.DEM_BLUR_RADIUS_INFO)
                    self.blur_radius_input = st.number_input(
                        "Blur Radius",
                        value=DEFAULT_BLUR_RADIUS,
                        min_value=0,
                        max_value=300,
                        key="blur_radius",
                        step=2,
                    )

                    st.write(Messages.DEM_PLATEAU_INFO)
                    self.plateau_height_input = st.number_input(
                        "Plateau Height",
                        value=0,
                        min_value=0,
                        max_value=10000,
                        key="plateau_height",
                    )

                    st.write(Messages.WATER_DEPTH_INFO)
                    self.water_depth = st.number_input(
                        "Water Depth",
                        value=200,
                        min_value=0,
                        max_value=10000,
                        key="water_depth",
                    )

                with st.expander("Textures Advanced Settings", icon="🎨"):
                    st.info(
                        "ℹ️ Settings related to the textures of the map, which represent different "
                        "types of terrain, such as grass, dirt, etc."
                    )

                    st.write(Messages.FIELD_PADDING_INFO)
                    self.fields_padding = st.number_input(
                        "Field Padding",
                        value=0,
                        min_value=0,
                        max_value=100,
                        key="field_padding",
                    )

                    st.write(Messages.DISSOLVING_INFO)
                    self.dissolving_enabled = st.checkbox(
                        "Texture dissolving",
                        value=True,
                        key="dissolving_enabled",
                    )

                    st.write(Messages.SKIP_DRAINS_INFO)
                    self.skip_drains = st.checkbox(
                        "Skip drains",
                        value=False,
                        key="skip_drains",
                    )

                with st.expander("Farmlands Advanced Settings", icon="🌾"):
                    st.info(
                        "ℹ️ Settings related to the farmlands of the map, which represent the lands "
                        "that can be bought in the game by the player."
                    )

                    st.write(Messages.FARMLAND_MARGIN_INFO)

                    self.farmland_margin = st.number_input(
                        "Farmland Margin",
                        value=3,
                        min_value=0,
                        max_value=100,
                        key="farmland_margin",
                    )

                    st.write(Messages.ADD_FARMYARDS_INFO)

                    self.add_farmyards = st.checkbox(
                        "Add farmyards",
                        value=False,
                        key="add_farmyards",
                    )

                with st.expander("Vegetation Advanced Settings", icon="🌲"):
                    st.info(
                        "ℹ️ Settings related to the vegetation of the map, which represent the trees, "
                        "grass, etc."
                    )

                    st.write(Messages.FOREST_DENSITY_INFO)
                    self.forest_density = st.number_input(
                        "Forest Density",
                        value=10,
                        min_value=2,
                        max_value=50,
                        key="forest_density",
                    )

                    st.write(Messages.RANDOMIZE_PLANTS_INFO)
                    self.randomize_plants = st.checkbox(
                        "Random plants", value=True, key="randomize_plants"
                    )

                with st.expander("Background Advanced Settings", icon="🖼️"):
                    st.info(
                        "ℹ️ Settings related to the background of the map, which represent the "
                        "surrounding area of the map."
                    )

                    st.write(Messages.GENERATE_BACKGROUND_INFO)
                    self.generate_background = st.checkbox(
                        "Generate background", value=True, key="generate_background"
                    )

                    st.write(Messages.GENERATE_WATER_INFO)
                    self.generate_water = st.checkbox(
                        "Generate water", value=True, key="generate_water"
                    )

                    st.write(Messages.BACKGROUND_RESIZE_FACTOR_INFO)

                    if self.public:
                        disabled = True
                        st.warning(Messages.SETTING_LOCAL)
                    else:
                        disabled = False

                    self.background_resize_factor = st.number_input(
                        "Background Resize Factor",
                        value=8,
                        min_value=1,
                        max_value=16,
                        key="background_resize_factor",
                        disabled=disabled,
                    )

                with st.expander("Spline Advanced Settings", icon="🛤️"):
                    st.info(
                        "ℹ️ Settings related to the spline component of the map, which represent the "
                        "roads, paths, etc."
                    )

                    st.write(Messages.SPLINE_DENSITY_INFO)

                    self.spline_density = st.number_input(
                        "Spline Density",
                        value=2,
                        min_value=0,
                        max_value=10,
                        key="spline_density",
                    )

        self.custom_schemas = False
        self.texture_schema_input = None
        self.tree_schema_input = None

        if self.game_code == "FS25":
            self.custom_schemas = st.checkbox(
                "Show schemas editor", value=False, key="custom_schemas"
            )

            if self.custom_schemas:
                self.logger.debug("Custom schemas are enabled.")

                st.warning("⚠️ Changing these settings can lead to unexpected results.")

                with st.expander("Texture custom schema", icon="🎨"):
                    st.write("Enter the texture schema:")
                    st.write(Messages.TEXTURE_SCHEMA_INFO)

                    with open(config.FS25_TEXTURE_SCHEMA_PATH, "r", encoding="utf-8") as f:
                        schema = json.load(f)

                    self.texture_schema_input = st.text_area(
                        "Texture Schema",
                        value=json.dumps(schema, indent=2),
                        height=600,
                        label_visibility="collapsed",
                    )

                with st.expander("Tree custom schema", icon="🌲"):
                    st.write("Enter the tree schema:")
                    st.write(Messages.TEXTURE_SCHEMA_INFO)

                    with open(config.FS25_TREE_SCHEMA_PATH, "r", encoding="utf-8") as f:
                        schema = json.load(f)

                    self.tree_schema_input = st.text_area(
                        "Tree Schema",
                        value=json.dumps(schema, indent=2),
                        height=600,
                        label_visibility="collapsed",
                    )

        # Add an empty container for status messages.
        self.status_container = st.empty()

        # Add an empty container for buttons.
        self.buttons_container = st.empty()

        # Generate button.
        with self.buttons_container:
            if not config.is_on_community_server():
                if st.button("Generate", key="launch_btn"):
                    self.generate_map()

        # Download button.
        if st.session_state.generated:
            self.logger.debug("Generated was set to True in the session state.")
            with open(self.download_path, "rb") as f:
                with self.buttons_container:
                    st.download_button(
                        label="Download",
                        data=f,
                        file_name=f"{self.download_path.split('/')[-1]}",
                        mime="application/zip",
                        icon="📥",
                    )

            config.remove_with_delay_without_blocking(self.download_path, self.logger)

            st.session_state.generated = False
            self.logger.debug("Generated was set to False in the session state.")

    def get_sesion_name(self, coordinates: tuple[float, float]) -> str:
        """Return a session name for the map, using the coordinates and the current timestamp.

        Arguments:
            coordinates (tuple[float, float]): The latitude and longitude of the center point of
                the map.

        Returns:
            str: The session name for the map.
        """
        coordinates_str = "_".join(map(self.shorten_coordinate, coordinates))
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        return f"{self.game_code}_{coordinates_str}_{timestamp}"

    def shorten_coordinate(self, coordinate: float) -> str:
        """Shorten a coordinate to a string.

        Arguments:
            coordinate (float): The coordinate to shorten.

        Returns:
            str: The shortened coordinate.
        """
        return f"{coordinate:.5f}".replace(".", "_")

    def generate_map(self) -> None:
        """Generate the map."""
        game = mfs.Game.from_code(self.game_code)

        try:
            lat, lon = self.lat_lon
        except ValueError:
            st.error("Invalid latitude and longitude!")
            return

        # Prepare a tuple with the coordinates of the center point of the map.
        coordinates = (lat, lon)

        # Read map size from the input widget.
        try:
            height, width = self.map_size
        except ValueError:
            st.error("Invalid map size!")
            return

        if height % 2 != 0 or width % 2 != 0:
            st.error("Map size must be a power of 2. For example: 2, 4, ... 2048, 4096, ...")
            return

        if height != width:
            st.error("Map size must be square (height == width).")
            return

        # Session name will be used for a directory name as well as a zip file name.

        session_name = self.get_sesion_name(coordinates)

        map_directory = os.path.join(config.MAPS_DIRECTORY, session_name)
        os.makedirs(map_directory, exist_ok=True)

        if not self.expert_mode:
            multiplier = self.multiplier_input if not self.auto_process else 1

            plateau = (
                self.plateau_height_input
                if not self.water_depth
                else self.plateau_height_input + self.water_depth
            )

            dem_settings = mfs.DEMSettings(
                auto_process=self.auto_process,
                multiplier=multiplier,
                blur_radius=self.blur_radius_input,
                plateau=plateau,
                water_depth=self.water_depth,
            )
            self.logger.debug("DEM settings: %s", dem_settings)

            background_settings = mfs.BackgroundSettings(
                generate_background=self.generate_background,
                generate_water=self.generate_water,
                resize_factor=self.background_resize_factor,
            )
            self.logger.debug("Background settings: %s", background_settings)

            grle_settings = mfs.GRLESettings(
                farmland_margin=self.farmland_margin,
                random_plants=self.randomize_plants,
                add_farmyards=self.add_farmyards,
            )
            self.logger.debug("GRLE settings: %s", grle_settings)

            i3d_settings = mfs.I3DSettings(forest_density=self.forest_density)
            self.logger.debug("I3D settings: %s", i3d_settings)

            texture_settings = mfs.TextureSettings(
                dissolve=self.dissolving_enabled,
                fields_padding=self.fields_padding,
                skip_drains=self.skip_drains,
            )
            self.logger.debug("Texture settings: %s", texture_settings)

            spline_settings = mfs.SplineSettings(spline_density=self.spline_density)

        else:
            if self.raw_config is not None:
                try:
                    raw_config = json.loads(self.raw_config)
                    all_settings = mfs.SettingsModel.all_settings_from_json(raw_config)
                    dem_settings = all_settings["DEMSettings"]
                    background_settings = all_settings["BackgroundSettings"]

                    if self.public:
                        # Override the background resize factor for the public server.
                        background_settings = mfs.BackgroundSettings(
                            generate_background=background_settings.generate_background,
                            generate_water=background_settings.generate_water,
                            resize_factor=8,
                        )

                    grle_settings = all_settings["GRLESettings"]
                    i3d_settings = all_settings["I3DSettings"]
                    texture_settings = all_settings["TextureSettings"]
                    spline_settings = all_settings["SplineSettings"]

                    config_save_path = os.path.join(map_directory, "raw_config.json")
                    with open(config_save_path, "w", encoding="utf-8") as f:
                        json.dump(raw_config, f, indent=4)

                except Exception as e:
                    st.error(f"Invalid raw configuration: {repr(e)}")
                    return

        texture_schema = None
        tree_schema = None
        if self.custom_schemas:
            if self.texture_schema_input:
                try:
                    texture_schema = json.loads(self.texture_schema_input)
                except json.JSONDecodeError:
                    st.error("Invalid texture schema!")
                    return
            if self.tree_schema_input:
                try:
                    tree_schema = json.loads(self.tree_schema_input)
                except json.JSONDecodeError:
                    st.error("Invalid tree schema!")
                    return

        if self.custom_osm_enabled:
            osm_path = self.custom_osm_path
        else:
            osm_path = None

        mp = mfs.Map(
            game,
            coordinates,
            height,
            self.rotation,
            map_directory,
            logger=self.logger,
            custom_osm=osm_path,
            dem_settings=dem_settings,
            background_settings=background_settings,
            grle_settings=grle_settings,
            i3d_settings=i3d_settings,
            texture_settings=texture_settings,
            spline_settings=spline_settings,
            texture_custom_schema=texture_schema,
            tree_custom_schema=tree_schema,
        )

        if self.public:
            add_to_queue(session_name)
            for position in wait_in_queue(session_name):
                self.status_container.info(
                    f"Your position in the queue: {position}. Please wait...", icon="⏳"
                )

            self.status_container.info("Started the map generation...", icon="🔄")

        try:
            step = int(100 / (len(game.components) + 2))
            completed = 0
            progress_bar = st.progress(0)

            generation_started_at = perf_counter()
            for component_name in mp.generate():
                progress_bar.progress(completed, f"⏳ Generating {component_name}...")
                completed += step

            completed += step
            progress_bar.progress(completed, "🖼️ Creating previews...")

            # Create a preview image.
            self.show_preview(mp)
            self.map_preview()

            completed += step
            progress_bar.progress(completed, "🗃️ Packing the map...")

            # Pack the generated map into a zip archive.
            archive_path = mp.pack(os.path.join(config.ARCHIVES_DIRECTORY, session_name))

            self.download_path = archive_path

            st.session_state.generated = True

            generation_finished_at = perf_counter()
            generation_time = round(generation_finished_at - generation_started_at, 3)
            self.logger.info("Map generated in %s seconds.", generation_time)
            self.status_container.success(f"Map generated in {generation_time} seconds.", icon="✅")
        except Exception as e:
            self.logger.error("An error occurred while generating the map: %s", repr(e))
            self.status_container.error(
                f"An error occurred while generating the map: {repr(e)}.", icon="❌"
            )
        finally:
            if self.public:
                remove_from_queue(session_name)

    def show_preview(self, mp: mfs.Map) -> None:
        """Show the preview of the generated map.

        Arguments:
            mp (Map): The generated map.
        """
        # Get a list of all preview images.
        full_preview_paths = mp.previews()
        if not full_preview_paths:
            # In case if generation of the preview images failed, we will not show them.
            return

        with self.preview_container:
            st.markdown("---")
            st.write("Previews of the generated map:")

            image_preview_paths = [
                preview for preview in full_preview_paths if preview.endswith(".png")
            ]

            columns = st.columns(len(image_preview_paths))
            for column, image_preview_path in zip(columns, image_preview_paths):
                if not os.path.isfile(image_preview_path):
                    continue
                try:
                    image = Image.open(image_preview_path)
                    column.image(image, use_container_width=True)
                except Exception:
                    continue

            stl_preview_paths = [
                preview for preview in full_preview_paths if preview.endswith(".stl")
            ]

            for stl_preview_path in stl_preview_paths:
                if not os.path.isfile(stl_preview_path):
                    continue
                try:
                    stl_from_file(
                        file_path=stl_preview_path,
                        color="#808080",
                        material="material",
                        auto_rotate=True,
                        height="400",
                        key=None,
                        max_view_distance=10000,
                    )
                except Exception:
                    continue
