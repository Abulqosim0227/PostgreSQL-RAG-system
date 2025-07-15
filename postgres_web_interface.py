
import streamlit as st
import pandas as pd
import time
from postgres_rag_system import PostgreSQLRAGSystem

# Configure Streamlit page
st.set_page_config(
    page_title="PostgreSQL RAG Search",
    page_icon="🔍",
    layout="wide"
)

# Initialize the system (cached for performance)
@st.cache_resource
def init_postgres_rag():
    """Initialize and cache the PostgreSQL RAG system"""
    return PostgreSQLRAGSystem(
        host="localhost",
        database="postgres", 
        user="postgres",
        password="123456",
        port=5432
    )

# Main App
def main():
    st.title("🐘 PostgreSQL RAG Search System")
    st.markdown("Search **HS Codes** and **Descriptions** from your `m_classifier_hs1` table")
    
    # Initialize system
    with st.spinner("Initializing PostgreSQL RAG system..."):
        postgres_rag = init_postgres_rag()
    
    # Sidebar for system info
    st.sidebar.markdown("## 🔧 System Info")
    st.sidebar.info(f"""
    **Database:** postgres@localhost:5432
    **Table:** m_classifier_hs1
    **Columns:** cs_code, cs_fullname
    **Search Engine:** Meilisearch + SentenceTransformers
    """)
    
    # Test Connection Button
    if st.sidebar.button("🔌 Test Connection"):
        with st.spinner("Testing database connection..."):
            success = postgres_rag.test_connection()
            if success:
                st.sidebar.success("✅ Database connected!")
            else:
                st.sidebar.error("❌ Connection failed!")
    
    # Index Data Button
    if st.sidebar.button("📊 Index Database"):
        with st.spinner("Indexing m_classifier_hs1 table..."):
            success = postgres_rag.index_m_classifier_hs1()
            if success:
                st.sidebar.success("✅ Indexing completed!")
            else:
                st.sidebar.error("❌ Indexing failed!")
    
    # Main search interface
    st.markdown("---")
    
    # Create two columns for different search types
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 🔍 Search by Description")
        st.markdown("*Enter a description to find matching HS codes*")
        
        description_query = st.text_input(
            "Description:",
            placeholder="e.g., 'live animals', 'meat products', 'dairy'",
            key="desc_search"
        )
        
        if st.button("Search Codes", key="search_codes"):
            if description_query:
                with st.spinner("Searching for codes..."):
                    result = postgres_rag.ask_description_return_code(description_query)
                
                if result["found"]:
                    st.success(f"✅ Found {result['total_results']} results")
                    
                    # Best match
                    best = result["best_match"]
                    st.markdown("#### 🎯 Best Match:")
                    st.info(f"**Code:** {best['code']}")
                    st.info(f"**Description:** {best['description']}")
                    
                    # All results in a table
                    st.markdown("#### 📊 All Results:")
                    results_df = pd.DataFrame(result["results"])
                    st.dataframe(results_df, use_container_width=True)
                    
                else:
                    st.error(f"❌ No results found for '{description_query}'")
                    st.info("💡 Try different keywords or check spelling")
    
    with col2:
        st.markdown("### 🔢 Search by Code")
        st.markdown("*Enter an HS code to find its description*")
        
        code_query = st.text_input(
            "HS Code:",
            placeholder="e.g., '0101', '0201', '0301'",
            key="code_search"
        )
        
        if st.button("Search Description", key="search_desc"):
            if code_query:
                with st.spinner("Looking up code..."):
                    result = postgres_rag.get_code_description(code_query)
                
                if result["found"]:
                    st.success("✅ Code found!")
                    st.info(f"**Code:** {result['code']}")
                    st.info(f"**Description:** {result['description']}")
                else:
                    st.error(f"❌ Code '{code_query}' not found")
                    st.info("💡 Check the code format and try again")
    
    # Batch search feature
    st.markdown("---")
    st.markdown("### 📋 Batch Search")
    
    search_type = st.selectbox(
        "Search Type:",
        ["Search multiple descriptions", "Search multiple codes"]
    )
    
    if search_type == "Search multiple descriptions":
        batch_input = st.text_area(
            "Enter descriptions (one per line):",
            placeholder="live animals\nmeat products\ndairy products\nvegetables\nfruits",
            height=100
        )
        
        if st.button("Batch Search Codes"):
            if batch_input:
                queries = [q.strip() for q in batch_input.split('\n') if q.strip()]
                
                progress_bar = st.progress(0)
                results_data = []
                
                for i, query in enumerate(queries):
                    result = postgres_rag.ask_description_return_code(query)
                    
                    if result["found"]:
                        best = result["best_match"]
                        results_data.append({
                            "Query": query,
                            "Status": "✅ Found",
                            "Best Code": best["code"],
                            "Best Description": best["description"],
                            "Total Results": result["total_results"]
                        })
                    else:
                        results_data.append({
                            "Query": query,
                            "Status": "❌ Not Found",
                            "Best Code": "-",
                            "Best Description": "-",
                            "Total Results": 0
                        })
                    
                    progress_bar.progress((i + 1) / len(queries))
                
                st.success(f"✅ Batch search completed! {len(results_data)} queries processed")
                results_df = pd.DataFrame(results_data)
                st.dataframe(results_df, use_container_width=True)
    
    else:  # Search multiple codes
        batch_input = st.text_area(
            "Enter codes (one per line):",
            placeholder="0101\n0201\n0301\n0401\n0501",
            height=100
        )
        
        if st.button("Batch Search Descriptions"):
            if batch_input:
                codes = [c.strip() for c in batch_input.split('\n') if c.strip()]
                
                progress_bar = st.progress(0)
                results_data = []
                
                for i, code in enumerate(codes):
                    result = postgres_rag.get_code_description(code)
                    
                    if result["found"]:
                        results_data.append({
                            "Code": code,
                            "Status": "✅ Found",
                            "Description": result["description"]
                        })
                    else:
                        results_data.append({
                            "Code": code,
                            "Status": "❌ Not Found",
                            "Description": "-"
                        })
                    
                    progress_bar.progress((i + 1) / len(codes))
                
                st.success(f"✅ Batch search completed! {len(results_data)} codes processed")
                results_df = pd.DataFrame(results_data)
                st.dataframe(results_df, use_container_width=True)
    
    # Footer
    st.markdown("---")
    st.markdown("### 🎯 How to Use")
    st.markdown("""
    1. **First Time Setup:** Click "Index Database" to index your PostgreSQL data
    2. **Search by Description:** Enter any description to find matching HS codes
    3. **Search by Code:** Enter an HS code to find its description
    4. **Batch Search:** Process multiple queries at once
    
    **Examples:**
    - Description: "live animals" → Find codes like 0101, 0102, etc.
    - Code: "0101" → Find description: "Live horses, asses, mules..."
    """)
    
    st.info("💡 **Tip:** The system uses AI-powered semantic search, so you can use natural language descriptions!")

if __name__ == "__main__":
    main() 