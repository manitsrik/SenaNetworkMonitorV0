from database import Database
import json

def test_save():
    db = Database()
    
    # Test Data
    name = "Test Dashboard via Script"
    layout = [
        {"type": "stat_card", "title": "Test Widget", "width": 4, "height": 150, "config": {}}
    ]
    layout_str = json.dumps(layout)
    
    print(f"Attempting to create dashboard: {name}")
    try:
        result = db.create_dashboard(
            name=name,
            layout_config=layout_str,
            description="Created by test script",
            created_by=1, # Admin ID
            is_public=1
        )
        print(f"Result: {result}")
        
        if result['success']:
            dashboard_id = result['id']
            print(f"Successfully created dashboard with ID: {dashboard_id}")
            
            # Test Update
            print(f"Attempting to update dashboard: {dashboard_id}")
            update_layout = layout + [{"type": "gauge", "title": "New", "width": 4, "height": 350, "config": {}}]
            update_result = db.update_dashboard(
                dashboard_id,
                name=name + " Updated",
                layout_config=json.dumps(update_layout)
            )
            print(f"Update Result: {update_result}")
            
            # Verify
            saved = db.get_dashboard(dashboard_id)
            print(f"Saved layout_config type: {type(saved['layout_config'])}")
            print(f"Saved layout_config value: {saved['layout_config'][:100]}...")
            
    except Exception as e:
        print(f"Error occurred: {e}")

if __name__ == "__main__":
    test_save()
