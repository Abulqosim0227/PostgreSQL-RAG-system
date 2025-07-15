
import psycopg2
import pandas as pd
from typing import Dict, List, Any, Optional
import json
import requests
import torch
from sentence_transformers import SentenceTransformer
import time

class PostgreSQLRAGSystem:
    def __init__(self, 
                 host="localhost", 
                 database="postgres", 
                 user="postgres", 
                 password="123456", 
                 port=5432,
                 meilisearch_url="http://localhost:7700", 
                 master_key="mySecretKey"):
        #Db bilan ulanish
        
        self.db_config = {
            'host': host,
            'database': database,
            'user': user,
            'password': password,
            'port': port
        }
        
        self.meilisearch_url = meilisearch_url
        self.master_key = master_key
        self.index_name = "postgres_classifier_hs1"
        
        # Configure requests (proxy bypass + auth)
        self.proxies = {'http': None, 'https': None}
        self.headers = {
            'Authorization': f'Bearer {master_key}',
            'Content-Type': 'application/json'
        }
        
        # model agar sizda cuda bo'lsa cuda, aks holda cpu ishlatiladi
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.text_model = SentenceTransformer('all-MiniLM-L6-v2')
        
        print("🐘 PostgreSQL RAG System Initialized!")
        print(f"   Database: {database}@{host}:{port}")
        print(f"   User: {user}")
        print(f"   Meilisearch: {meilisearch_url}")
        print(f"   Index: {self.index_name}")
    
    def connect_to_postgres(self) -> psycopg2.extensions.connection:
        """Connect to PostgreSQL database"""
        try:
            conn = psycopg2.connect(**self.db_config)
            print(f"✅ Connected to PostgreSQL: {self.db_config['database']}")
            return conn
        except Exception as e:
            print(f"❌ PostgreSQL connection failed: {e}")
            return None
    
    def test_connection(self):
        #db bilan ulanishni tekshirish
        conn = self.connect_to_postgres()
        if not conn:
            return False
        
        try:
            cursor = conn.cursor()
            
            # Test basic connection
            cursor.execute("SELECT version();")
            version = cursor.fetchone()
            print(f"📋 PostgreSQL Version: {version[0][:50]}...")
            
            # table mavjudligini tekshirish
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'm_classifier_hs1'
                );
            """)
            table_exists = cursor.fetchone()[0]
            print(f"📊 Table m_classifier_hs1 exists: {table_exists}")
            
            if table_exists:
                # table strukturasini olish
                cursor.execute("""
                    SELECT column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_name = 'm_classifier_hs1'
                    ORDER BY ordinal_position;
                """)
                columns = cursor.fetchall()
                print("📋 Table Structure:")
                for col_name, col_type in columns:
                    print(f"   - {col_name}: {col_type}")
                
                # Get row count
                cursor.execute("SELECT COUNT(*) FROM m_classifier_hs1;")
                row_count = cursor.fetchone()[0]
                print(f"📊 Total rows: {row_count}")
                
                # Show sample data
                cursor.execute("SELECT cs_code, cs_fullname FROM m_classifier_hs1 LIMIT 5;")
                samples = cursor.fetchall()
                print("📋 Sample Data:")
                for code, fullname in samples:
                    print(f"   - {code}: {fullname}")
            
            conn.close()
            return True
            
        except Exception as e:
            print(f"❌ Database test failed: {e}")
            conn.close()
            return False
    
    def setup_meilisearch_index(self):
        """Configure Meilisearch for PostgreSQL data"""
        try:
            # Create index
            response = requests.post(
                f"{self.meilisearch_url}/indexes",
                json={"uid": self.index_name, "primaryKey": "id"},
                proxies=self.proxies,
                headers=self.headers
            )
            print(f"Index creation: {response.status_code}")
            
            # Configure filterable attributes
            filter_config = {
                "filterableAttributes": ["cs_code", "category", "type"],
                "searchableAttributes": ["cs_code", "cs_fullname", "content"],
                "sortableAttributes": ["cs_code"]
            }
            
            filter_response = requests.patch(
                f"{self.meilisearch_url}/indexes/{self.index_name}/settings",
                json=filter_config,
                proxies=self.proxies,
                headers=self.headers
            )
            
            print(f"Filter configuration: {filter_response.status_code}")
            return response.status_code in [201, 202]
            
        except Exception as e:
            print(f"Error setting up index: {e}")
            return False
    
    def index_m_classifier_hs1(self):
        """Index the m_classifier_hs1 table"""
        conn = self.connect_to_postgres()
        if not conn:
            return False
        
        try:
            # Setup Meilisearch index
            self.setup_meilisearch_index()
            
            # Query PostgreSQL
            query = "SELECT cs_code, cs_fullname FROM m_classifier_hs1;"
            df = pd.read_sql_query(query, conn)
            
            print(f"📊 Found {len(df)} records to index")
            
            # Index each row
            indexed_count = 0
            for index, row in df.iterrows():
                # Create searchable content
                content = f"Code: {row['cs_code']} | Name: {row['cs_fullname']}"
                
                # Generate embedding
                embedding = self.text_model.encode([content])[0].tolist()
                
                # Create document for Meilisearch
                document = {
                    "id": f"classifier_{row['cs_code']}",
                    "cs_code": row['cs_code'],
                    "cs_fullname": row['cs_fullname'],
                    "content": content,
                    "embedding": embedding,
                    "type": "classifier",
                    "category": "hs_code"
                }
                
                # Add to Meilisearch
                response = requests.post(
                    f"{self.meilisearch_url}/indexes/{self.index_name}/documents",
                    json=[document],
                    proxies=self.proxies,
                    headers=self.headers
                )
                
                if response.status_code == 202:
                    indexed_count += 1
                    if indexed_count % 100 == 0:  # Show progress every 100 records
                        print(f"✅ Indexed {indexed_count} records...")
                else:
                    print(f"❌ Failed to index: {row['cs_code']} - {response.text}")
            
            conn.close()
            print(f"🎉 Successfully indexed {indexed_count} records!")
            return True
            
        except Exception as e:
            print(f"❌ Error indexing database: {e}")
            conn.close()
            return False
    
    def search_classifier(self, query: str, limit: int = 5) -> List[Dict]:
        """Search the classifier data"""
        try:
            search_params = {
                "q": query,
                "limit": limit,
                "attributesToRetrieve": ["cs_code", "cs_fullname", "content"]
            }
            
            response = requests.post(
                f"{self.meilisearch_url}/indexes/{self.index_name}/search",
                json=search_params,
                proxies=self.proxies,
                headers=self.headers
            )
            
            if response.status_code == 200:
                results = response.json().get("hits", [])
                return results
            else:
                print(f"Search failed: {response.status_code} - {response.text}")
                return []
                
        except Exception as e:
            print(f"Search error: {e}")
            return []
    
    def ask_description_return_code(self, description_query: str) -> Dict:
        """Ask for description and return code + description"""
        print(f"🤔 Query: {description_query}")
        
        # Search for matching descriptions
        results = self.search_classifier(description_query, limit=5)
        
        if not results:
            return {
                "query": description_query,
                "found": False,
                "message": "No matching codes found",
                "suggestions": ["Try different keywords", "Check spelling", "Use broader terms"]
            }
        
        # Format results
        formatted_results = []
        for result in results:
            formatted_results.append({
                "code": result.get("cs_code", ""),
                "description": result.get("cs_fullname", ""),
                "relevance": result.get("_score", 0)
            })
        
        return {
            "query": description_query,
            "found": True,
            "total_results": len(results),
            "results": formatted_results,
            "best_match": {
                "code": formatted_results[0]["code"],
                "description": formatted_results[0]["description"]
            } if formatted_results else None
        }
    
    def get_code_description(self, code: str) -> Dict:
        """Get description for a specific code"""
        print(f"🔍 Looking up code: {code}")
        
        # Search for exact code match
        results = self.search_classifier(code, limit=1)
        
        if not results:
            return {
                "code": code,
                "found": False,
                "message": "Code not found"
            }
        
        result = results[0]
        return {
            "code": result.get("cs_code", ""),
            "description": result.get("cs_fullname", ""),
            "found": True
        }

# Initialize the PostgreSQL RAG system
print("🚀 Initializing PostgreSQL RAG System...")
postgres_rag = PostgreSQLRAGSystem(
    host="localhost",
    database="postgres", 
    user="postgres",
    password="123456",
    port=5432
) 