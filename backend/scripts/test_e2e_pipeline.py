import httpx
import time
import sys
import json

BASE_URL = "http://127.0.0.1:8080/api/v1"

def test_pipeline():
    print(f"Starting E2E test against {BASE_URL}...")
    
    # Step 1: Start generation
    start_payload = {
        "topic": "Why digital authenticity and verified communities matter",
        "duration": 30,
        "style": "educational"
    }
    print(f"Sending generation request: {json.dumps(start_payload, indent=2)}")
    
    try:
        r = httpx.post(f"{BASE_URL}/generate", json=start_payload, timeout=30.0)
        r.raise_for_status()
    except httpx.RequestError as e:
        print(f"Connection error: Could not reach the server at {BASE_URL}. Is it running?")
        print(f"Details: {e}")
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"HTTP error: {e.response.status_code} - {e.response.text}")
        sys.exit(1)
        
    data = r.json()
    job_id = data.get("job_id")
    print(f"\nJob started successfully. ID: {job_id}\n")
    
    # Step 3: Poll for status
    while True:
        try:
            r = httpx.get(f"{BASE_URL}/status/{job_id}", timeout=10.0)
            r.raise_for_status()
            status_data = r.json()
        except Exception as e:
            print(f"Failed to poll status: {e}")
            sys.exit(1)
            
        status = status_data.get("status")
        stage = status_data.get("stage")
        progress = status_data.get("progress")
        error_msg = status_data.get("error")
        
        # Step 4: Print progress
        print(f"[{status}] {stage} ... {progress}%")
        
        # Step 5: Handle failure
        if status == "failed":
            print(f"\nJob failed! Error: {error_msg}")
            sys.exit(1)
            
        # Step 6: Handle completion
        if status == "completed":
            print("\nJob completed successfully!")
            break
            
        time.sleep(3)

    # Step 7: Get result
    try:
        res = httpx.get(f"{BASE_URL}/result/{job_id}", timeout=10.0)
        res.raise_for_status()
        result_data = res.json()
    except Exception as e:
        print(f"Failed to fetch final result: {e}")
        sys.exit(1)

    # Step 8: Pretty print highlight
    print("\n" + "="*50)
    print("FINAL RESULT")
    print("="*50)
    print(f"Title:     {result_data.get('title')}")
    print(f"Hook:      {result_data.get('hook')}")
    print(f"Video URL: {result_data.get('video_url')}")
    print("="*50)
    
    print("\nFull JSON Response:")
    print(json.dumps(result_data, indent=2))

if __name__ == "__main__":
    test_pipeline()
