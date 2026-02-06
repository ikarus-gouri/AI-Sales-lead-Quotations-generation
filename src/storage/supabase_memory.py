"""
Supabase Memory Layer - Learning & Replay System
Stores configurator states, transitions, and patterns for intelligent replay.
"""

import os
import hashlib
import json
from typing import Optional, Dict, List, Any, Tuple
from datetime import datetime

try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    Client = None


class SupabaseMemory:
    """
    Memory layer for learning configurator patterns and enabling replay.
    
    - Records page states and transitions
    - Tracks success/failure confidence
    - Enables replay without LLM calls when confidence is high
    - Provides cross-run and cross-site learning
    """
    
    def __init__(self, enabled: bool = True):
        """
        Initialize Supabase memory client.
        
        Args:
            enabled: Whether to use Supabase (auto-disabled if credentials missing)
        """
        self.client: Optional[Client] = None
        self.enabled = enabled and SUPABASE_AVAILABLE
        
        if not SUPABASE_AVAILABLE:
            print("⚠️  Supabase not available (install: pip install supabase)")
            self.enabled = False
            return
        
        if not enabled:
            print("ℹ️  Supabase memory disabled by configuration")
            return
        
        # Try to initialize client
        try:
            supabase_url = os.getenv("SUPABASE_URL")
            supabase_key = os.getenv("SUPABASE_ANON_KEY")
            
            if not supabase_url or not supabase_key:
                print("⚠️  Supabase credentials not configured (SUPABASE_URL, SUPABASE_ANON_KEY)")
                self.enabled = False
                return
            
            self.client = create_client(supabase_url, supabase_key)
            print("✓ Supabase memory layer initialized")
            
        except Exception as e:
            print(f"⚠️  Failed to initialize Supabase: {e}")
            self.enabled = False
            self.client = None
    
    def is_enabled(self) -> bool:
        """Check if Supabase memory is available and enabled."""
        return self.enabled and self.client is not None
    
    # ============================================================
    # STATE MANAGEMENT
    # ============================================================
    
    def upsert_state(
        self,
        site_domain: str,
        url_path: str,
        page_signature: str,
        model_name: str,
        step_index: int,
        is_terminal: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Record or update a page state.
        
        Args:
            site_domain: Domain of the site (e.g., "example.com")
            url_path: URL path (e.g., "/configure")
            page_signature: Computed hash of page structure
            model_name: Product model/variant name
            step_index: Step number in configuration flow
            is_terminal: Whether this is a final state
            
        Returns:
            State record with ID, or None if failed
        """
        if not self.is_enabled():
            return None
        
        try:
            result = self.client.table("states").upsert({
                "site_domain": site_domain,
                "url_path": url_path,
                "page_signature": page_signature,
                "model_name": model_name,
                "step_index": step_index,
                "is_terminal": is_terminal,
                "created_at": datetime.now().isoformat()
            }, on_conflict="site_domain,page_signature").execute()
            
            return result.data[0] if result.data else None
            
        except Exception as e:
            print(f"⚠️  Failed to upsert state: {e}")
            return None
    
    def get_state_by_signature(
        self,
        site_domain: str,
        page_signature: str
    ) -> Optional[Dict[str, Any]]:
        """Get existing state by signature."""
        if not self.is_enabled():
            return None
        
        try:
            result = self.client.table("states").select("*").eq(
                "site_domain", site_domain
            ).eq(
                "page_signature", page_signature
            ).execute()
            
            return result.data[0] if result.data else None
            
        except Exception as e:
            print(f"⚠️  Failed to get state: {e}")
            return None
    
    # ============================================================
    # TRANSITION TRACKING
    # ============================================================
    
    def record_transition(
        self,
        from_state_id: str,
        to_state_id: str,
        action_type: str,
        selector_pattern: Dict[str, Any],
        success: bool = True
    ) -> bool:
        """
        Record a transition between states.
        
        Args:
            from_state_id: UUID of source state
            to_state_id: UUID of destination state
            action_type: Type of action (e.g., "click", "select")
            selector_pattern: Pattern used to find element (for replay)
            success: Whether the transition succeeded
            
        Returns:
            True if recorded successfully
        """
        if not self.is_enabled():
            return False
        
        try:
            # Check if transition exists
            existing = self.client.table("transitions").select("*").eq(
                "from_state", from_state_id
            ).eq(
                "to_state", to_state_id
            ).eq(
                "action_type", action_type
            ).execute()
            
            if existing.data:
                # Update existing transition
                transition_id = existing.data[0]["id"]
                field = "success_count" if success else "failure_count"
                current_value = existing.data[0][field]
                
                self.client.table("transitions").update({
                    field: current_value + 1,
                    "last_used": datetime.now().isoformat()
                }).eq("id", transition_id).execute()
            else:
                # Create new transition
                self.client.table("transitions").insert({
                    "from_state": from_state_id,
                    "to_state": to_state_id,
                    "action_type": action_type,
                    "selector_pattern": json.dumps(selector_pattern),
                    "success_count": 1 if success else 0,
                    "failure_count": 0 if success else 1,
                    "last_used": datetime.now().isoformat()
                }).execute()
            
            return True
            
        except Exception as e:
            print(f"⚠️  Failed to record transition: {e}")
            return False
    
    def get_confident_transition(
        self,
        from_state_id: str,
        min_success_rate: float = 0.8,
        min_seen_count: int = 3
    ) -> Optional[Dict[str, Any]]:
        """
        Get a high-confidence transition for replay (avoids LLM call).
        
        Args:
            from_state_id: Source state UUID
            min_success_rate: Minimum success rate (default: 80%)
            min_seen_count: Minimum times seen (default: 3)
            
        Returns:
            Transition data if confident, None otherwise
        """
        if not self.is_enabled():
            return None
        
        try:
            # Get all transitions from this state
            result = self.client.table("transitions").select("*").eq(
                "from_state", from_state_id
            ).execute()
            
            if not result.data:
                return None
            
            # Find best confident transition
            best_transition = None
            best_confidence = 0.0
            
            for transition in result.data:
                success = transition["success_count"]
                failure = transition["failure_count"]
                total = success + failure
                
                if total < min_seen_count:
                    continue
                
                success_rate = success / total if total > 0 else 0.0
                
                if success_rate >= min_success_rate and success_rate > best_confidence:
                    best_confidence = success_rate
                    best_transition = transition
            
            return best_transition
            
        except Exception as e:
            print(f"⚠️  Failed to get confident transition: {e}")
            return None
    
    # ============================================================
    # PATTERN LEARNING
    # ============================================================
    
    def upsert_continue_pattern(
        self,
        site_domain: str,
        pattern: Dict[str, Any],
        success: bool = True
    ) -> bool:
        """
        Record a "continue" button pattern with success tracking.
        
        Args:
            site_domain: Domain of the site
            pattern: Pattern dict (text, classes, position hints)
            success: Whether the pattern led to success
            
        Returns:
            True if recorded successfully
        """
        if not self.is_enabled():
            return False
        
        try:
            pattern_json = json.dumps(pattern)
            
            # Check if pattern exists
            existing = self.client.table("continue_patterns").select("*").eq(
                "site_domain", site_domain
            ).eq(
                "pattern", pattern_json
            ).execute()
            
            if existing.data:
                # Update existing
                record = existing.data[0]
                seen_count = record["seen_count"] + 1
                success_count = record.get("success_count", 0) + (1 if success else 0)
                success_rate = success_count / seen_count if seen_count > 0 else 0.0
                
                self.client.table("continue_patterns").update({
                    "success_rate": success_rate,
                    "seen_count": seen_count,
                    "success_count": success_count
                }).eq("id", record["id"]).execute()
            else:
                # Create new
                self.client.table("continue_patterns").insert({
                    "site_domain": site_domain,
                    "pattern": pattern_json,
                    "success_rate": 1.0 if success else 0.0,
                    "seen_count": 1,
                    "success_count": 1 if success else 0
                }).execute()
            
            return True
            
        except Exception as e:
            print(f"⚠️  Failed to upsert pattern: {e}")
            return False
    
    def get_best_continue_pattern(
        self,
        site_domain: str,
        min_success_rate: float = 0.8,
        min_seen_count: int = 3
    ) -> Optional[Dict[str, Any]]:
        """
        Get the most reliable "continue" button pattern for a site.
        
        Args:
            site_domain: Domain of the site
            min_success_rate: Minimum success rate
            min_seen_count: Minimum times seen
            
        Returns:
            Pattern dict or None
        """
        if not self.is_enabled():
            return None
        
        try:
            result = self.client.table("continue_patterns").select("*").eq(
                "site_domain", site_domain
            ).gte("success_rate", min_success_rate).gte(
                "seen_count", min_seen_count
            ).order("success_rate", desc=True).limit(1).execute()
            
            if result.data:
                pattern_str = result.data[0]["pattern"]
                return json.loads(pattern_str)
            
            return None
            
        except Exception as e:
            print(f"⚠️  Failed to get continue pattern: {e}")
            return None
    
    # ============================================================
    # UTILITIES
    # ============================================================
    
    def get_stats(self, site_domain: Optional[str] = None) -> Dict[str, Any]:
        """
        Get memory statistics.
        
        Args:
            site_domain: Optional domain filter
            
        Returns:
            Stats dict with counts and metrics
        """
        if not self.is_enabled():
            return {"enabled": False}
        
        try:
            stats = {"enabled": True}
            
            # State count
            if site_domain:
                states = self.client.table("states").select("id", count="exact").eq(
                    "site_domain", site_domain
                ).execute()
            else:
                states = self.client.table("states").select("id", count="exact").execute()
            stats["states"] = states.count if hasattr(states, 'count') else len(states.data)
            
            # Transition count
            if site_domain:
                transitions = self.client.table("transitions").select("id", count="exact").execute()
                # Filter would require joining with states - skip for simplicity
                stats["transitions"] = transitions.count if hasattr(transitions, 'count') else len(transitions.data)
            else:
                transitions = self.client.table("transitions").select("id", count="exact").execute()
                stats["transitions"] = transitions.count if hasattr(transitions, 'count') else len(transitions.data)
            
            # Pattern count
            if site_domain:
                patterns = self.client.table("continue_patterns").select("id", count="exact").eq(
                    "site_domain", site_domain
                ).execute()
            else:
                patterns = self.client.table("continue_patterns").select("id", count="exact").execute()
            stats["patterns"] = patterns.count if hasattr(patterns, 'count') else len(patterns.data)
            
            return stats
            
        except Exception as e:
            print(f"⚠️  Failed to get stats: {e}")
            return {"enabled": True, "error": str(e)}


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def compute_page_signature(page_state: Dict[str, Any]) -> str:
    """
    Compute a stable signature for a page state.
    
    Uses element structure (not content) to identify similar pages.
    
    Args:
        page_state: Page state dict with 'elements' list
        
    Returns:
        Hex hash string (signature)
    """
    sig_parts = []
    
    elements = page_state.get("elements", [])
    for elem in elements[:50]:  # Limit to first 50 elements for performance
        # Use tag, classes, and approximate position
        tag = elem.get("tag", "")
        classes = elem.get("classes", "")[:30]  # Truncate long class strings
        position = elem.get("position", {})
        y_bucket = position.get("y", 0) // 100  # Group by 100px vertical bands
        
        sig_parts.append(f"{tag}|{classes}|{y_bucket}")
    
    # Sort for stability (order may vary slightly)
    sig_parts.sort()
    
    # Hash the signature
    signature_str = "|".join(sig_parts)
    return hashlib.sha256(signature_str.encode()).hexdigest()


def extract_site_domain(url: str) -> str:
    """
    Extract domain from URL.
    
    Args:
        url: Full URL
        
    Returns:
        Domain string (e.g., "example.com")
    """
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return parsed.netloc.replace("www.", "")


def create_selector_pattern(element: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a reusable selector pattern from an element.
    
    Args:
        element: Element dict from page state
        
    Returns:
        Pattern dict for replay
    """
    return {
        "tag": element.get("tag"),
        "classes": element.get("classes", "")[:50],
        "text": element.get("text", "")[:50],
        "attributes": {
            k: v for k, v in element.get("attributes", {}).items()
            if k in ["id", "name", "data-*", "aria-label"]
        }
    }
