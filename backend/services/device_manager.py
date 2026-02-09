import time
from typing import Dict, Optional, List
from services.firebase_db import firebase_db
from firebase_admin import db

class DeviceManager:
    """Manages device registration, active device locking, and device lifecycle."""
    
    DEVICE_TIMEOUT = 300  # 5 minutes in seconds
    
    def register_device(self, user_id: str, device_id: str, device_info: Dict) -> bool:
        """
        Register a device for a user.
        
        Args:
            user_id: User's UID
            device_id: Unique device identifier
            device_info: {name, platform, userAgent}
        """
        if not user_id or not device_id:
            return False
            
        try:
            ref = db.reference(f'users/{user_id}/devices/{device_id}')
            ref.set({
                'name': device_info.get('name', 'Unknown Device'),
                'platform': device_info.get('platform', 'web'),
                'userAgent': device_info.get('userAgent', ''),
                'lastSeen': {'.sv': 'timestamp'},
                'isOnline': True
            })
            
            # If this is the first device, make it active
            active_device = self.get_active_device(user_id)
            if not active_device:
                self.set_active_device(user_id, device_id)
            
            return True
        except Exception as e:
            print(f"Error registering device: {e}")
            return False
    
    def set_active_device(self, user_id: str, device_id: str) -> bool:
        """
        Set the active playback device for a user.
        Only the active device can control playback.
        """
        if not user_id or not device_id:
            return False
            
        try:
            # Verify device exists
            device_ref = db.reference(f'users/{user_id}/devices/{device_id}')
            device = device_ref.get()
            
            if not device:
                print(f"Device {device_id} not found for user {user_id}")
                return False
            
            # Set as active
            playback_ref = db.reference(f'users/{user_id}/playback')
            playback_ref.update({'activeDeviceId': device_id})
            
            return True
        except Exception as e:
            print(f"Error setting active device: {e}")
            return False
    
    def get_active_device(self, user_id: str) -> Optional[str]:
        """Get the currently active device ID for a user."""
        if not user_id:
            return None
            
        try:
            ref = db.reference(f'users/{user_id}/playback/activeDeviceId')
            return ref.get()
        except Exception as e:
            print(f"Error getting active device: {e}")
            return None
    
    def update_device_heartbeat(self, user_id: str, device_id: str) -> bool:
        """Update device's last seen timestamp to keep it alive."""
        if not user_id or not device_id:
            return False
            
        try:
            ref = db.reference(f'users/{user_id}/devices/{device_id}')
            ref.update({
                'lastSeen': {'.sv': 'timestamp'},
                'isOnline': True
            })
            return True
        except Exception as e:
            print(f"Error updating heartbeat: {e}")
            return False
    
    def get_user_devices(self, user_id: str) -> List[Dict]:
        """Get all devices for a user with online status."""
        if not user_id:
            return []
            
        try:
            ref = db.reference(f'users/{user_id}/devices')
            devices_data = ref.get()
            
            if not devices_data:
                return []
            
            devices = []
            current_time = time.time() * 1000  # Convert to milliseconds
            
            for device_id, device_info in devices_data.items():
                last_seen = device_info.get('lastSeen', 0)
                is_online = (current_time - last_seen) < (self.DEVICE_TIMEOUT * 1000)
                
                devices.append({
                    'id': device_id,
                    'name': device_info.get('name'),
                    'platform': device_info.get('platform'),
                    'lastSeen': last_seen,
                    'isOnline': is_online
                })
            
            return devices
        except Exception as e:
            print(f"Error getting user devices: {e}")
            return []
    
    def cleanup_stale_devices(self, user_id: str) -> int:
        """Remove devices that haven't been seen in >5 minutes."""
        if not user_id:
            return 0
            
        try:
            ref = db.reference(f'users/{user_id}/devices')
            devices_data = ref.get()
            
            if not devices_data:
                return 0
            
            current_time = time.time() * 1000
            removed_count = 0
            
            for device_id, device_info in devices_data.items():
                last_seen = device_info.get('lastSeen', 0)
                if (current_time - last_seen) > (self.DEVICE_TIMEOUT * 1000):
                    device_ref = db.reference(f'users/{user_id}/devices/{device_id}')
                    device_ref.delete()
                    removed_count += 1
            
            return removed_count
        except Exception as e:
            print(f"Error cleaning up devices: {e}")
            return 0
    
    def validate_device_control(self, user_id: str, device_id: str) -> bool:
        """
        Check if a device is allowed to control playback.
        Returns True only if device_id matches activeDeviceId.
        """
        if not user_id or not device_id:
            return False
            
        active_device = self.get_active_device(user_id)
        return device_id == active_device

device_manager = DeviceManager()
