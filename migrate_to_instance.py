#!/usr/bin/env python3
"""
Migration script to convert existing data files to instance-based format.
Run this script to migrate your existing users.json, contacts.json, and events.json
to instance-specific files.
"""

import os
import json
import shutil
from datetime import datetime

def migrate_data(instance_id: str, backup: bool = True):
    """
    Migrate existing data files to instance-specific format.
    
    Args:
        instance_id: The instance ID to use (e.g., 'reeves_capstone', 'mj_capstone')
        backup: Whether to create backup copies of original files
    """
    files_to_migrate = {
        'users.json': f'users_{instance_id}.json',
        'contacts.json': f'contacts_{instance_id}.json',
        'events.json': f'events_{instance_id}.json'
    }
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    print(f"Migrating data to instance: {instance_id}")
    print("-" * 50)
    
    for old_file, new_file in files_to_migrate.items():
        if os.path.exists(old_file):
            # Create backup if requested
            if backup:
                backup_file = f"{old_file}.backup_{timestamp}"
                shutil.copy2(old_file, backup_file)
                print(f"✓ Backed up {old_file} → {backup_file}")
            
            # Copy to new instance-specific file
            shutil.copy2(old_file, new_file)
            print(f"✓ Migrated {old_file} → {new_file}")
            
            # Optionally remove old file (commented out for safety)
            # os.remove(old_file)
            # print(f"✓ Removed {old_file}")
        else:
            print(f"⚠ {old_file} not found, skipping...")
    
    # Create instance_config.json
    config = {
        "instance_id": instance_id,
        "description": f"Migrated on {datetime.now().isoformat()}",
        "migrated_from": "legacy files"
    }
    
    with open('instance_config.json', 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)
    
    print(f"\n✓ Created instance_config.json with instance_id: {instance_id}")
    print("\nMigration complete!")
    print(f"\nNext steps:")
    print(f"1. Verify your data files: users_{instance_id}.json, contacts_{instance_id}.json, events_{instance_id}.json")
    print(f"2. Start the application - it will automatically use instance_id: {instance_id}")
    print(f"3. If everything works, you can safely delete the old .json files and backup files")

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python migrate_to_instance.py <instance_id> [--no-backup]")
        print("\nExample:")
        print("  python migrate_to_instance.py reeves_capstone")
        print("  python migrate_to_instance.py mj_capstone")
        print("  python migrate_to_instance.py school_a --no-backup")
        sys.exit(1)
    
    instance_id = sys.argv[1]
    backup = '--no-backup' not in sys.argv
    
    # Sanitize instance ID
    instance_id = ''.join(c for c in instance_id if c.isalnum() or c in ('-', '_')) or 'default'
    
    if instance_id == 'default':
        print("Warning: Using 'default' as instance ID. Consider using a more descriptive name.")
        response = input("Continue? (y/n): ")
        if response.lower() != 'y':
            sys.exit(0)
    
    migrate_data(instance_id, backup)

