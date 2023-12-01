import streamlit as st
import pandas as pd
import psycopg2
import uuid
import requests
from openai import OpenAI
from io import BytesIO
from bs4 import BeautifulSoup
import os


GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')
GOOGLE_CX = os.environ.get('GOOGLE_CX')
DB_NAME = os.environ.get('DB_NAME')
DB_USER = os.environ.get('DB_USER')
DB_PASSWORD = os.environ.get('DB_PASSWORD')
DB_HOST = os.environ.get('DB_HOST')
DB_PORT = os.environ.get('DB_PORT')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
GOOGLE_ENDPOINT='https://customsearch.googleapis.com/customsearch/v1'

# Modify the client instantiation for OpenAI
client = OpenAI(api_key=OPENAI_API_KEY)

# Constants from populate.py
DISEASES = ["MYELOMA", "ALS", "PARKINSON", "STROKE", "ALZHEIMER"]
CATEGORIES = ["GENERAL", "EMOTIONAL", "HOME_CARE", "FINANCIAL_LEGAL"]


connection_string = (
    f"dbname='{DB_NAME}' "
    f"user='{DB_USER}' "
    f"password='{DB_PASSWORD}' "
    f"host='{DB_HOST}' "
    f"port='{DB_PORT}'"
)
# Database Connection String


def fetch_content_from_url(url):
    response = requests.get(url)
    return response.text

def parse_website_content(content):
    title = get_concise_title_from_gpt(content)
    description = get_concise_description_from_gpt(content)  # Now using GPT-4 for description

    # Handling cases where no description is generated
    if not description:
        description = "No description available"

    return title, description

def get_concise_description_from_gpt(content):
    prompt = f"You are a helpful summarizer. Please provide a concise summary of the following website content:\n\n{content}\n\n"

    response = client.chat.completions.create(
        model="gpt-4-1106-preview",
        messages=[
            {"role": "system", "content": "You are a helpful summarizer."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=200,  # Adjust as needed
    )
    description = response.choices[0].message.content.strip()
    return description

def get_concise_title_from_gpt(content):
    prompt = f"You are a helpful summarizer that takes in website information and returns a comprehensive title of the information found on that site. Here is the website information:\n\n{content}\n\nPlease provide a summarized title for this content."

    response = client.chat.completions.create(
        model="gpt-4-1106-preview",
        messages=[
            {"role": "system", "content": "You are a helpful summarizer."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=60,
    )
    title = response.choices[0].message.content.strip()
    return title


def get_gpt_response(prompt):
    response = client.chat.completions.create(
        model="gpt-4-1106-preview",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=200,
    )
    message_content = response.choices[0].message.content
    return message_content.strip()


def extract_exact_category_or_disease(response, choices):
    for choice in choices:
        if choice.lower() in response.lower():
            return choice
    return "Unknown"

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

def remove_non_diseases(df, selected_disease):
    # Filter the DataFrame to keep only rows where the 'Disease' matches the selected disease
    filtered_df = df[df['Disease'] == selected_disease]
    return filtered_df



# Search Resources
def search_resources(query, selected_types, location_filter, selected_disease):
    # Configuration for Google Search
    def get_google_search_results(query, selected_types, location_filter):
        query_terms = [query] + selected_types
        if location_filter:
            query_terms.append(location_filter)
        full_query = " ".join(query_terms) + " support organization non-profit"

        params = {
            'key': GOOGLE_API_KEY,
            'cx': GOOGLE_CX,
            'q': full_query,
            'num': 5
        }
        response = requests.get(GOOGLE_ENDPOINT, params=params)
        return response.json().get('items', [])

    # Process search results with OpenAI
    def process_with_openai(items):
        
        input_text = "Format the following search results into a readable summary:\n"
        for item in items:
            input_text += f"Title: {item['title']}\nLink: {item['link']}\nDescription: {item['snippet']}\n\n"
        
        messages = [
            {"role": "system", "content": "You are an assistant that creates concise, informative summaries of search results, highlighting key details and providing context."},
            {"role": "user", "content": input_text}
        ]
        response = client.chat.completions.create(
            model="gpt-4-1106-preview",
            messages=messages,
            max_tokens=300,
        )
        message_content = response.choices[0].message.content
        return message_content.strip()

    items = get_google_search_results(query, selected_types, location_filter)
    summary = process_with_openai(items)  # Process the search results for summary

    # Process each item to determine disease and category
    updated_data = []
    for item in items:
        url = item['link']
        content = fetch_content_from_url(url)
        title, description = parse_website_content(content)

        disease = selected_disease

        category_prompt = f"Based on the title: {title} and description: {description}, which category from the list {CATEGORIES} best matches?"
        category_response = get_gpt_response(category_prompt).strip()
        category = extract_exact_category_or_disease(category_response, CATEGORIES)

        updated_row = {
            'Title': title,
            'Description': description,
            'Link': url,
            'Category': category,
            'Image': 'NaN',  # Placeholder for image
            'Disease': disease
        }
        
        updated_data.append(updated_row)

    updated_df = pd.DataFrame(updated_data, columns=['Title', 'Description', 'Link', 'Category', 'Image', 'Disease'])

    return summary, updated_df

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
            To find organizations and services that provide specific support to caregivers, enter your search query below. This tool focuses on identifying websites of non-profit organizations, support groups, healthcare navigation services, financial assistance programs, technology tools, legal support, and community programs. Please note that the search will exclude articles and blog posts.
        """)

        # Add checkboxes for selecting resource types
        st.markdown("Select the type of resources you are interested in:")
        resource_types = ['Support Groups', 'Financial Assistance', 'Healthcare Navigation', 'Technology Tools', 'Legal Support', 'Community Programs']
        selected_types = st.multiselect('Resource Types', resource_types)

        # Dropdown for disease selection with no default selection
        st.markdown("Select the disease:")
        selected_disease = st.selectbox('Select a Disease (Choose one)', [''] + DISEASES, index=0)

        # Add an optional geographical filter
        location_filter = st.text_input("Enter a location to filter (optional):")

        # Text input for search query
        query = st.text_input("Enter Search Query")

        # Search button - activate only if a disease is selected and a query is entered
        if selected_disease and query and st.button("Search Resources"):
            # Call the function to search resources based on the query, selected types, and location filter
            summary, search_results_df = search_resources(query, selected_types, location_filter, selected_disease)
            
            if not search_results_df.empty:
                st.write(summary)
                towrite = BytesIO()
                search_results_df.to_excel(towrite, index=False)
                towrite.seek(0)
                st.download_button(label="Download Search Results", data=towrite, file_name='search_results.xlsx')
            else:
                st.warning("No results found. Please try a different query or selection.")
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