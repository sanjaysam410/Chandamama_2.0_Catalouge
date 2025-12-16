import streamlit as st
import requests
import base64
import json
import time
import os
import re

# --- Configuration ---
API_KEY = ""  # To be filled by user or environment
MODEL_NAME = "gemini-2.5-flash-preview-09-2025"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent"
GLOBAL_STATS_PATH = "global_stats.json"

# --- Helper Functions ---

def get_book_id(filename):
    """
    Derives BOOK_ID from filename.
    Example: "Chandamama 1947 11.pdf" -> "chandamama_1947_11"
    """
    # Remove extension
    name = os.path.splitext(filename)[0]
    # Replace spaces with underscores and convert to lowercase
    book_id = re.sub(r'\s+', '_', name).lower()
    return book_id

def calculate_statistics(data):
    """
    Calculates author and genre statistics and adds them to the data object.
    """
    stories = data.get('stories', [])
    author_counts = {}
    genre_counts = {}

    for i, story in enumerate(stories):
        # --- Robust Page Calculation ---
        # Logic: book_page_end = book_page_start + (pdf_page_end - pdf_page_start)
        try:
            pdf_start = int(story.get('pdf_page_start', 0))
            pdf_end = int(story.get('pdf_page_end', 0))
            book_start = story.get('book_page_start')
            
            # If book_start is missing, try to infer from previous story
            if book_start is None or book_start == 0:
                if i > 0:
                    prev_story = stories[i-1]
                    prev_end = prev_story.get('book_page_end', 0)
                    if prev_end:
                         # Assumption: distinct stories usually start on new pages, but could be same page.
                         # Defaulting to prev_end + 1 is a safe heuristic for now.
                        book_start = prev_end + 1
                        story['book_page_start'] = book_start

            if book_start and pdf_start and pdf_end:
                page_count = pdf_end - pdf_start
                book_end = book_start + page_count
                story['book_page_end'] = book_end
            else:
                 story['book_page_end'] = None # Could not calculate
        except (ValueError, TypeError):
             story['book_page_end'] = None

        # --- Statistics ---
        # Count Authors
        author = story.get('author', 'చందమామ బృందం').strip()
        if author and author.lower() != 'unknown':
            author_counts[author] = author_counts.get(author, 0) + 1
            
        # Count Genres
        genre = story.get('genre', 'Unknown').strip()
        if genre and genre.lower() != 'unknown':
            genre_counts[genre] = genre_counts.get(genre, 0) + 1
            
    # Add statistics block to the top level
    data['statistics'] = {
        'total_stories': len(stories),
        'author_counts': author_counts,
        'genre_counts': genre_counts
    }
    return data

def load_global_stats():
    """Loads global statistics from the JSON file."""
    if os.path.exists(GLOBAL_STATS_PATH):
        try:
            with open(GLOBAL_STATS_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {"total_stories": 0, "authors": {}, "genres": {}}
    return {"total_stories": 0, "authors": {}, "genres": {}}

def save_global_stats(stats):
    """Saves global statistics to the JSON file."""
    try:
        with open(GLOBAL_STATS_PATH, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving global stats: {e}")

def update_global_stats(new_data):
    """Updates global statistics with data from a newly processed file."""
    stats = load_global_stats()
    
    stories = new_data.get('stories', [])
    stats['total_stories'] = stats.get('total_stories', 0) + len(stories)
    
    # Initialize dictionaries if missing
    if 'authors' not in stats: stats['authors'] = {}
    if 'genres' not in stats: stats['genres'] = {}

    for story in stories:
        # Update Authors
        author = story.get('author', 'చందమామ బృందం').strip()
        if author:
            stats['authors'][author] = stats['authors'].get(author, 0) + 1
            
        # Update Genres
        genre = story.get('genre', 'Unknown').strip()
        if genre and genre.lower() != 'unknown':
            stats['genres'][genre] = stats['genres'].get(genre, 0) + 1
            
    save_global_stats(stats)
    return stats

def encode_pdf(file):
    """Encodes the uploaded PDF file to Base64."""
    return base64.b64encode(file.read()).decode('utf-8')

def get_structured_index(pdf_base64, api_key):
    """
    Sends the PDF to Gemini API and retrieves the structured index.
    """
    headers = {
        "Content-Type": "application/json"
    }
    
    system_instruction = """
    Role: Expert Chandamama Magazine Indexer.
    Task 1: Locate the Index/Table of Contents page.
    Task 2: Extract `title`.
    Task 3: Extract Page Numbers:
        - `book_page_start`: The **PRINTED page number** visible on the magazine page.
        - `pdf_page_start` & `pdf_page_end`: The **PDF sequence numbers** (1-indexed) corresponding to the story.
    Task 4: Navigate to that start page to find the `author`. If the author is explicitly named, capture it. If NOT found, default to "చందమామ బృందం".
    Task 5: Extract the full text content of the story as `content`. Preserve paragraph structure. NEVER truncate content.
    Task 6: Extract `moral`, `genre` (e.g., Fable, Mythology, History, Humor), `keywords` (3-5 tags), `characters` (list), and `locations` (list).

    CRITICAL LANGUAGE RULES:
    1. `content`, `moral`, `characters`, `keywords`, `locations`, `genre`: MUST be in **TELUGU**.
    2. `author`: Extract as it appears (usually Telugu). Defaults to "చందమామ బృందం".

    CRITICAL EXTRACTION RULES:
    1. "ఆహ్వానము" (Ahwanamu) is an Editorial/Introduction. Treat it as a completely SEPARATE story/entry. DO NOT merge it with the next story.
    2. Watch closely for the end of a story (e.g., "The End", "సమాప్తం", or distinct visual separators) and the START of a new title.
    3. If a new big title appears, that is a NEW story. Stop extracting content for the current story immediately.
    4. Do not combine multiple different contents into one entry.
    5. Maintain separate entries for every distinct story/article.

    Output: Return a strictly formatted JSON object.
    """

    prompt = """
    Extract the index and content from this Chandamama magazine.
    Return a JSON object with the following schema:
    {
        "book_id": "string",
        "stories": [
            {
                "title": "string",
                "book_page_start": int,
                "pdf_page_start": int,
                "pdf_page_end": int,
                "author": "string",
                "genre": "string",
                "moral": "string",
                "keywords": ["string"],
                "characters": ["string"],
                "locations": ["string"],
                "content": "string"
            }
        ]
    }
    """

    data = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {
                    "inline_data": {
                        "mime_type": "application/pdf",
                        "data": pdf_base64
                    }
                }
            ]
        }],
        "system_instruction": {
            "parts": [{"text": system_instruction}]
        },
        "generationConfig": {
            "response_mime_type": "application/json"
        }
    }

    params = {
        "key": api_key
    }

    # Exponential backoff retry logic
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(API_URL, headers=headers, params=params, json=data)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                st.warning(f"Attempt {attempt + 1} failed. Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                st.error(f"Maximum retries reached. Failed to get response from API: {e}")
                if response is not None:
                     st.error(f"API Response: {response.text}")
                return None

# --- UI Layout ---

def render_single_mode():
    st.header("Single File Processing")
    
    # API Key Input (if not hardcoded)
    api_key_input = st.text_input("Enter Gemini API Key", value=API_KEY, type="password")
    if not api_key_input:
        st.warning("Please enter your API Key to proceed.")
        st.stop()

    # File Upload
    uploaded_file = st.file_uploader("Upload Chandamama PDF", type=["pdf"])

    if uploaded_file:
        book_id = get_book_id(uploaded_file.name)
        st.info(f"Processing Book ID: `{book_id}`")

        # Initialize session state for this file if not present
        if 'current_file' not in st.session_state or st.session_state['current_file'] != uploaded_file.name:
            st.session_state['current_file'] = uploaded_file.name
            st.session_state['indexed_data'] = None

        # Step 1: Analyze
        if st.button("Analyze PDF"):
            with st.spinner("Analyzing PDF with Gemini... This may take a minute."):
                # Reset file pointer to beginning before reading
                uploaded_file.seek(0)
                pdf_base64 = encode_pdf(uploaded_file)
                
                api_response = get_structured_index(pdf_base64, api_key_input)
                
                if api_response:
                    try:
                        # Extract JSON from the response
                        content_text = api_response['candidates'][0]['content']['parts'][0]['text']
                        # Clean up markdown code blocks if present
                        content_text = content_text.replace("```json", "").replace("```", "").strip()
                        
                        data = json.loads(content_text)
                        
                        # Enforce book_id from filename if not present or different (optional, but good for consistency)
                        data['book_id'] = book_id
                        
                        # Calculate Statistics
                        data = calculate_statistics(data)
                        
                        # Update Global Stats
                        update_global_stats(data)

                        st.session_state['indexed_data'] = data
                        st.success("Analysis Complete!")
                    except (KeyError, json.JSONDecodeError) as e:
                        st.error(f"Failed to parse API response: {e}")
                        st.text(api_response)

        # Step 2: Verify
        if st.session_state.get('indexed_data'):
            st.subheader("Verify Extracted Data")
            
            data = st.session_state['indexed_data']
            stories = data.get('stories', [])
            
            if stories:
                # Display as editable dataframe (optional, but st.dataframe is good for viewing)
                # st.data_editor could be used if we wanted to allow edits, but requirements said "Verify"
                st.dataframe(stories, use_container_width=True)
                
                # Step 3: Download
                st.subheader("Download JSON")
                
                # Construct filename: YYYY/YYYY_MM.json
                # Try to extract year and month from book_id
                # Expected format: chandamama_1947_11
                parts = book_id.split('_')
                year = "Unknown"
                month = "Unknown"
                
                # Simple heuristic to find year (4 digits)
                for part in parts:
                    if part.isdigit() and len(part) == 4:
                        year = part
                        break
                
                # Heuristic for month (2 digits, usually follows year)
                # This is a bit loose, but fits the example "chandamama_1947_11"
                if len(parts) >= 3:
                        # Assuming format name_year_month
                        if parts[-1].isdigit():
                            month = parts[-1]
                
                if year != "Unknown" and month != "Unknown":
                    download_filename = f"{year}/{year}_{month}.json"
                else:
                    download_filename = f"{book_id}.json"

                json_str = json.dumps(data, indent=4, ensure_ascii=False)
                
                st.download_button(
                    label=f"Download `{download_filename}`",
                    data=json_str,
                    file_name=os.path.basename(download_filename), # Browser only cares about the name, not path
                    mime="application/json"
                )
                
                st.caption(f"Suggested directory structure: `{download_filename}`")
                
            else:
                st.warning("No stories found in the response.")

def render_bulk_mode():
    st.header("Bulk Processing")
    
    api_key_input = st.text_input("Enter Gemini API Key", value=API_KEY, type="password")
    if not api_key_input:
        st.warning("Please enter your API Key to proceed.")
        st.stop()

    # Input: Directory Path
    input_dir = st.text_input("Enter Directory Path containing PDFs (e.g., C:/Chandamama/1947)")
    
    # Input: Output Directory Path
    default_output = os.path.join(input_dir, "json") if input_dir else ""
    output_dir = st.text_input("Enter Output Directory for JSONs", value=default_output)

    if input_dir and os.path.isdir(input_dir):
        # Scan for PDFs
        pdf_files = [f for f in os.listdir(input_dir) if f.lower().endswith('.pdf')]
        st.success(f"Found {len(pdf_files)} PDF files in `{input_dir}`")
        
        # Initialize Bulk Session State
        if 'bulk_data' not in st.session_state:
            st.session_state['bulk_data'] = {} # {filename: {'status': ..., 'data': ..., 'verified': ...}}
            
            # Try to load backup if exists
            backup_path = os.path.join(input_dir, "_bulk_progress_backup.json")
            if os.path.exists(backup_path):
                try:
                    with open(backup_path, "r", encoding='utf-8') as f:
                        st.session_state['bulk_data'] = json.load(f)
                    st.info("Restored progress from backup file.")
                except Exception as e:
                    st.warning(f"Found backup file but failed to load it: {e}")

        # Start Processing Button
        if st.button("Start Batch Processing"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            stop_button = st.empty() # Placeholder for stop button logic if we could (Streamlit doesn't support interrupt easily inside loop without rerun)
            
            backup_path = os.path.join(input_dir, "_bulk_progress_backup.json")

            for i, filename in enumerate(pdf_files):
                # Check if already processed
                if filename in st.session_state['bulk_data'] and st.session_state['bulk_data'][filename].get('status') == 'processed':
                    progress_bar.progress((i + 1) / len(pdf_files))
                    continue 
                
                status_text.text(f"Processing {filename} ({i+1}/{len(pdf_files)})...")
                
                file_path = os.path.join(input_dir, filename)
                book_id = get_book_id(filename)
                
                try:
                    with open(file_path, "rb") as f:
                        pdf_base64 = base64.b64encode(f.read()).decode('utf-8')
                    
                    api_response = get_structured_index(pdf_base64, api_key_input)
                    
                    if api_response:
                        content_text = api_response['candidates'][0]['content']['parts'][0]['text']
                        content_text = content_text.replace("```json", "").replace("```", "").strip()
                        data = json.loads(content_text)
                        data['book_id'] = book_id
                        
                        # Calculate Statistics
                        data = calculate_statistics(data)

                        st.session_state['bulk_data'][filename] = {
                            'status': 'processed',
                            'data': data,
                            'verified': False
                        }
                    else:
                        st.session_state['bulk_data'][filename] = {'status': 'error', 'msg': 'API Error'}
                        
                except Exception as e:
                    st.session_state['bulk_data'][filename] = {'status': 'error', 'msg': str(e)}
                
                # Auto-save backup after every file
                try:
                    with open(backup_path, "w", encoding='utf-8') as f:
                        json.dump(st.session_state['bulk_data'], f, indent=4, ensure_ascii=False)
                except Exception as e:
                    st.warning(f"Failed to save backup: {e}")

                progress_bar.progress((i + 1) / len(pdf_files))
                time.sleep(1) # Rate limiting buffer
            
            status_text.text("Batch Processing Complete!")
            st.success(f"Processing finished. Backup saved to `{backup_path}`.")
            st.rerun()

        # --- Verification UI ---
        if st.session_state['bulk_data']:
            st.divider()
            st.subheader("Verification & Export")
            
            col1, col2 = st.columns([1, 3])
            
            with col1:
                st.write("### Files")
                # Create a list of files with status icons
                file_options = []
                for f in pdf_files:
                    status = st.session_state['bulk_data'].get(f, {}).get('status', 'pending')
                    verified = st.session_state['bulk_data'].get(f, {}).get('verified', False)
                    icon = "✅" if verified else ("🟢" if status == 'processed' else ("🔴" if status == 'error' else "⚪"))
                    file_options.append(f"{icon} {f}")
                
                selected_option = st.radio("Select File to Verify", file_options)
                selected_filename = selected_option.split(" ", 1)[1] if selected_option else None

            with col2:
                if selected_filename:
                    file_info = st.session_state['bulk_data'].get(selected_filename, {})
                    
                    if file_info.get('status') == 'processed':
                        st.write(f"### Editing: `{selected_filename}`")
                        
                        # Data Editor
                        current_data = file_info['data']
                        stories = current_data.get('stories', [])
                        
                        edited_stories = st.data_editor(stories, num_rows="dynamic", key=f"editor_{selected_filename}")
                        
                        # Update state with edits
                        file_info['data']['stories'] = edited_stories
                        
                        # Recalculate statistics after edits
                        file_info['data'] = calculate_statistics(file_info['data'])
                        
                        # Mark Verified Button
                        if st.button("Mark as Verified", key=f"verify_{selected_filename}"):
                            file_info['verified'] = True
                            
                            # Update Global Stats on verification
                            update_global_stats(file_info['data'])
                            
                            # Update backup immediately on verification
                            backup_path = os.path.join(input_dir, "_bulk_progress_backup.json")
                            with open(backup_path, "w", encoding='utf-8') as f:
                                json.dump(st.session_state['bulk_data'], f, indent=4, ensure_ascii=False)
                            
                            st.success(f"Marked `{selected_filename}` as Verified!")
                            st.rerun()
                            
                    elif file_info.get('status') == 'error':
                        st.error(f"Error processing file: {file_info.get('msg')}")
                    else:
                        st.info("File not processed yet.")

            # --- Export Section ---
            st.divider()
            st.write("### Export Verified Files")
            
            verified_count = sum(1 for v in st.session_state['bulk_data'].values() if v.get('verified'))
            st.write(f"Verified Files: {verified_count} / {len(pdf_files)}")
            
            if st.button("Generate JSONs for Verified Files"):
                if not output_dir:
                    st.error("Please specify an Output Directory.")
                else:
                    os.makedirs(output_dir, exist_ok=True)
                    
                    count = 0
                    for fname, info in st.session_state['bulk_data'].items():
                        if info.get('verified'):
                            data = info['data']
                            out_name = f"{data.get('book_id', os.path.splitext(fname)[0])}.json"
                            out_path = os.path.join(output_dir, out_name)
                            
                            with open(out_path, "w", encoding='utf-8') as f:
                                json.dump(data, f, indent=4, ensure_ascii=False)
                            count += 1
                    
                    st.success(f"Successfully generated {count} JSON files in `{output_dir}`")
    
    elif input_dir:
        st.error("Directory not found. Please check the path.")

# --- Main Execution ---

st.set_page_config(page_title="Chandamama Indexer", layout="wide")
st.title("Chandamama Magazine Indexer")

mode = st.sidebar.radio("Select Mode", ["Single File", "Bulk Processing"])

if mode == "Single File":
    render_single_mode()
else:
    render_bulk_mode()
