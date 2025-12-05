# Instance-Based Isolation Setup Guide

## Overview

This system now supports **instance-based isolation**, allowing multiple users/schools to run separate instances without data conflicts. Each instance has its own:
- Users database (`users_{instance_id}.json`)
- Contacts database (`contacts_{instance_id}.json`)
- Events database (`events_{instance_id}.json`)

## Quick Setup

### Method 1: Using Configuration File (Recommended)

1. **Copy the example config file:**
   ```bash
   cp instance_config.json.example instance_config.json
   ```

2. **Edit `instance_config.json`** and set your unique instance ID:
   ```json
   {
     "instance_id": "your_school_name",
     "description": "Your school or project identifier"
   }
   ```
   
   Examples:
   - `"instance_id": "reeves_capstone"` for Reeves' version
   - `"instance_id": "mj_capstone"` for Mark Joseph's version
   - `"instance_id": "school_a"` for School A
   - `"instance_id": "school_b"` for School B

3. **Run the application** - it will automatically use your instance ID.

### Method 2: Using Environment Variable

Set the `INSTANCE_ID` environment variable before running:

**Windows:**
```cmd
set INSTANCE_ID=your_instance_id
python app.py
```

**Linux/Mac:**
```bash
export INSTANCE_ID=your_instance_id
python app.py
```

**Or run in one line:**
```bash
INSTANCE_ID=your_instance_id python app.py
```

## Migration from Existing Installation

If you already have data in `users.json`, `contacts.json`, or `events.json`:

1. **Set your instance ID** (using Method 1 or 2 above)

2. **Rename existing files** to match your instance:
   ```bash
   # For instance_id = "reeves_capstone"
   mv users.json users_reeves_capstone.json
   mv contacts.json contacts_reeves_capstone.json
   mv events.json events_reeves_capstone.json
   ```

3. **Or keep default instance** - If you don't set an instance ID, it defaults to `"default"`, so:
   ```bash
   mv users.json users_default.json
   mv contacts.json contacts_default.json
   mv events.json events_default.json
   ```

## Multiple Instances on Same Machine

To run multiple instances simultaneously:

1. **Create separate directories** for each instance:
   ```bash
   mkdir instance_reeves
   mkdir instance_mj
   ```

2. **Copy the entire project** to each directory

3. **Set different instance IDs** in each:
   - `instance_reeves/instance_config.json` → `"instance_id": "reeves_capstone"`
   - `instance_mj/instance_config.json` → `"instance_id": "mj_capstone"`

4. **Run on different ports:**
   ```bash
   # Terminal 1 - Reeves' instance
   cd instance_reeves
   python app.py --port 5000
   
   # Terminal 2 - MJ's instance
   cd instance_mj
   python app.py --port 5001
   ```

## Important Notes

- **Instance ID Format**: Only alphanumeric characters, hyphens (-), and underscores (_) are allowed. Special characters are automatically removed.
- **Data Isolation**: Each instance's data is completely separate. Users, contacts, and events from one instance are not visible to another.
- **Default Instance**: If no instance ID is set, the system uses `"default"` as the instance ID.
- **Backward Compatibility**: Existing installations without instance config will continue to work with the `"default"` instance ID.

## Troubleshooting

**Q: My old data disappeared after setting instance ID**
A: Your data is still there, but it's looking for files with the new instance ID. Either:
- Rename your old files to match the new instance ID (see Migration section)
- Or remove `instance_config.json` to use the default instance

**Q: Can I share data between instances?**
A: No, each instance is isolated. If you need shared data, use the same instance ID.

**Q: What if I forget my instance ID?**
A: Check your `instance_config.json` file or look at the data file names in your directory (e.g., `users_reeves_capstone.json` means instance_id is `reeves_capstone`).

