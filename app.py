import streamlit as st
import pandas as pd
import psycopg2
import uuid
import requests
from openai import OpenAI
from io import BytesIO

GOOGLE_ENDPOINT = "https://customsearch.googleapis.com/customsearch/v1"
API_KEY = 'AIzaSyB0CnzLIRvJnP51_UtnCJLkb3RDIq_YdNg'
CX = '54a973ece6d92437a'


# Database Connection String
connection_string = (
    f"dbname='postgres' "
    f"user='postgres' "
    f"password='1OBkLRPpWQCrABWs' "
    f"host='db.kbwqfyazwecemnoujpgx.supabase.co' "
    f"port='5432'"
)

# Load data from Excel
def load_data_from_excel(file):
    return pd.read_excel(file)

# Send DataFrame to Database
def send_dataframe_to_database(df):
    with psycopg2.connect(connection_string) as conn:
        with conn.cursor() as cur:
            for _, record in df.iterrows():
                # Ensure 'record' is a dictionary
                record_dict = record.to_dict()
                record_dict['id'] = str(uuid.uuid4())
                
                columns = ', '.join(record_dict.keys())
                placeholders = ', '.join(['%s'] * len(record_dict))
                values = list(record_dict.values())
                
                cur.execute(f"INSERT INTO \"Resources\" ({columns}) VALUES ({placeholders});", values)
            conn.commit()


# Read Resources from Database
def read_resources_from_database():
    with psycopg2.connect(connection_string) as conn:
        return pd.read_sql("SELECT * FROM \"Resources\";", conn)

# Delete all Resources
def delete_all_resources():
    with psycopg2.connect(connection_string) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM \"Resources\";")
            conn.commit()

# Search Resources
def search_resources(query):
    # Configuration


    def get_google_search_results(query):
        params = {
            'key': API_KEY,
            'cx': CX,
            'q': query + " support resources",
            'num': 10
        }
        response = requests.get(GOOGLE_ENDPOINT, params=params)
        return response.json().get('items', [])


    def process_with_openai(items):
        client = OpenAI(api_key='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')
        input_text = "Format the following search results into a readable summary:\n"
        for item in items:
            input_text += f"Title: {item['title']}\nLink: {item['link']}\nDescription: {item['snippet']}\n\n"
        
        messages = [
            {"role": "system", "content": "You are an assistant that creates concise, informative summaries of search results, highlighting key details and providing context."},
            {"role": "user", "content": input_text}
        ]
        response = client.chat.completions.create(
            model="gpt-4-1106-preview",
            messages=messages
        )

        # Extracting the content from the response using the correct path
        message_content = response.choices[0].message.content
        return message_content.strip()


    items = get_google_search_results(query)
    summary = process_with_openai(items)
    data = [[item['title'], item['snippet'], item['link']] for item in items]
    df = pd.DataFrame(data, columns=['Title', 'Description', 'Link'])
    return summary, df

def verify_upload_data(data):
    return (data)

# Streamlit UI
def main():
    st.title("Resource Management Application")

    # Create tabs
    tab1, tab2, tab3 = st.tabs(["Mass Edit", "Crawling Function", "Mass Import"])

    # Tab 1: Mass Edit
    with tab1:
        st.markdown("""
            If you would like to edit the database, click 'Download Database' and you will be given an excel file to open. 
            Make any edits to any resources in the excel sheet. Once complete, upload the excel sheet into the 'Upload Edited Resources' 
            section. It will verify the format of the data and then upload it to the database.
        """)
        if st.button("Download Database"):
            df = read_resources_from_database()
            towrite = BytesIO()
            df.to_excel(towrite, index=False)
            towrite.seek(0)
            st.download_button(label="Download Excel", data=towrite, file_name='database.xlsx')

        uploaded_file = st.file_uploader("Upload Edited Resources", type="xlsx")
        if uploaded_file is not None and st.button("Replace Resources"):
            df = load_data_from_excel(uploaded_file)
            delete_all_resources()
            send_dataframe_to_database(df)
            st.success("Resources updated successfully.")

    # Tab 2: Crawling Function
    with tab2:
        st.markdown("""
            To crawl the internet for new resources, enter as specifically as possible what type of resource you would like. 
            Once the crawl is complete it will give you an excel file to open and make any edits. Once complete with those edits, 
            upload those resources and it will append them to the database.
        """)
        query = st.text_input("Enter Search Query")
        if query and st.button("Search Resources"):
            summary, search_results_df = search_resources(query)
            st.write(summary)
            towrite = BytesIO()
            search_results_df.to_excel(towrite, index=False)
            towrite.seek(0)
            st.download_button(label="Download Search Results", data=towrite, file_name='search_results.xlsx')

    # Tab 3: Mass Import
    with tab3:
        st.text("Upload a spreadsheet to add new resources to the database in bulk.")
        new_resources_file = st.file_uploader("Upload New Resources", type="xlsx", key="new-resources")
        if new_resources_file is not None and st.button("Add Resources"):
            new_df = load_data_from_excel(new_resources_file)
            send_dataframe_to_database(new_df)
            st.success("New resources added successfully.")

if __name__ == "__main__":
    main()