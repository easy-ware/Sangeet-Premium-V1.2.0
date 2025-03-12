
from datetime import datetime , timedelta , timezone
import logging
import ntplib
import pytz



logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)




class TimeConverter:
    """Handles time conversion between UTC and Indian Standard Time (IST)."""
    
    # IST offset from UTC is +5:30
    IST_OFFSET_HOURS = 5
    IST_OFFSET_MINUTES = 30
    
    @classmethod
    def utc_to_ist(cls, utc_dt):
        """Convert UTC datetime to IST datetime."""
        if not utc_dt:
            return None
            
        try:
            # Add IST offset
            ist_hours = utc_dt.hour + cls.IST_OFFSET_HOURS
            ist_minutes = utc_dt.minute + cls.IST_OFFSET_MINUTES
            
            # Handle minute overflow
            if ist_minutes >= 60:
                ist_hours += 1
                ist_minutes -= 60
            
            # Handle hour overflow
            if ist_hours >= 24:
                next_day = True
                ist_hours -= 24
            else:
                next_day = False
                
            # Create new datetime with IST values
            ist_dt = utc_dt.replace(hour=ist_hours, minute=ist_minutes)
            
            # Adjust date if needed
            if next_day:
                ist_dt = ist_dt + timedelta(days=1)
                
            return ist_dt
            
        except Exception as e:
            logger.error(f"UTC to IST conversion error: {e}")
            return utc_dt
    
    @classmethod
    def format_ist_timestamp(cls, dt, include_timezone=True):
        """Format datetime in IST format."""
        if not dt:
            return "Invalid Date"
            
        try:
            # Convert to IST if not already
            ist_dt = cls.utc_to_ist(dt)
            
            # Format with timezone indicator
            formatted = ist_dt.strftime('%Y-%m-%d %I:%M:%S %p')
            if include_timezone:
                formatted += " IST"
                
            return formatted
            
        except Exception as e:
            logger.error(f"IST formatting error: {e}")
            return "Invalid Date"
    
    @classmethod
    def format_relative_time(cls, dt):
        """Format time as relative (e.g., '2 hours ago')."""
        if not dt:
            return "Unknown time"
            
        try:
            now = datetime.now()
            ist_dt = cls.utc_to_ist(dt)
            diff = now - ist_dt
            
            seconds = diff.total_seconds()
            
            if seconds < 60:
                return "just now"
            elif seconds < 3600:
                minutes = int(seconds / 60)
                return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
            elif seconds < 86400:
                hours = int(seconds / 3600)
                return f"{hours} hour{'s' if hours != 1 else ''} ago"
            elif seconds < 604800:
                days = int(seconds / 86400)
                return f"{days} day{'s' if days != 1 else ''} ago"
            else:
                return ist_dt.strftime('%d %b %Y')
                
        except Exception as e:
            logger.error(f"Relative time formatting error: {e}")
            return "Unknown time"




from datetime import datetime
import pytz

class TimeSync:
    def __init__(self):
        self.ist = pytz.timezone('Asia/Kolkata')

    def get_current_time(self):
        return datetime.now(self.ist)

    def parse_datetime(self, dt_str):
        return datetime.fromisoformat(dt_str).astimezone(self.ist)

    def format_time(self, dt, relative=False):
        """Fast time formatting in IST."""
        if not isinstance(dt, datetime):
            dt = self.parse_datetime(dt)
        if relative:
            now = self.get_current_time()
            diff = now - dt
            minutes = diff.total_seconds() / 60
            if minutes < 60:
                return f"{int(minutes)}m ago"
            hours = minutes / 60
            if hours < 24:
                return f"{int(hours)}h ago"
            days = hours / 24
            return f"{int(days)}d ago"
        return dt.strftime('%Y-%m-%d %H:%M:%S')

