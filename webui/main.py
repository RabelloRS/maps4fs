import streamlit as st
from config import FAQ_MD, get_mds
from generator import GeneratorUI
from templates import Messages
from toolbox import ToolboxUI


class WebUI:
    def __init__(self):
        st.set_page_config(page_title="maps4FS", page_icon="🚜", layout="wide")
        generator_tab, toolbox_tab, knowledge_tab, faq_tab = st.tabs(
            ["🗺️ Map Generator", "🧰 Modder Toolbox", "📖 Knowledge base", "📝 FAQ"]
        )

        with generator_tab:
            self.generator = GeneratorUI()

        with toolbox_tab:
            self.toolbox = ToolboxUI()

        with knowledge_tab:
            st.title("Knowledge base")
            st.write(Messages.KNOWLEDGE_INFO)
            mds = get_mds()

            tabs = st.tabs(list(mds.keys()))

            for tab, md_path in zip(tabs, mds.values()):
                with tab:
                    st.write(open(md_path, "r").read())

        with faq_tab:
            st.write(open(FAQ_MD, "r").read())


WebUI()