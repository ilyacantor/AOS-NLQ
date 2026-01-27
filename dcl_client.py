import httpx
from typing import Optional, Dict, Any
import json

class DCLClient:
    """Client for communicating with DCLv2 data unification engine."""
    
    def __init__(self, endpoint_url: str, timeout: float = 30.0):
        self.endpoint_url = endpoint_url.rstrip("/")
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout)
    
    def query(self, natural_language_query: str, entity_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Send a natural language query to DCLv2 and get entity results.
        
        Args:
            natural_language_query: The user's question in plain English
            entity_type: Optional filter for specific entity types
            
        Returns:
            Dict containing the query results from DCLv2
        """
        payload = {
            "query": natural_language_query,
        }
        
        if entity_type:
            payload["entity_type"] = entity_type
        
        try:
            response = self.client.post(
                f"{self.endpoint_url}/query",
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {
                "status": "error",
                "message": f"HTTP error: {e.response.status_code}",
                "details": str(e)
            }
        except httpx.RequestError as e:
            return {
                "status": "error", 
                "message": "Connection error",
                "details": str(e)
            }
    
    def get_entities(self, entity_type: str, filters: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Fetch entities directly from DCLv2.
        
        Args:
            entity_type: The type of entity to fetch
            filters: Optional filters to apply
            
        Returns:
            Dict containing the entities
        """
        params = {"type": entity_type}
        if filters:
            params["filters"] = json.dumps(filters)
        
        try:
            response = self.client.get(
                f"{self.endpoint_url}/entities",
                params=params
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }
    
    def health_check(self) -> bool:
        """Check if DCLv2 endpoint is reachable."""
        try:
            response = self.client.get(f"{self.endpoint_url}/health")
            return response.status_code == 200
        except Exception:
            return False
    
    def close(self):
        """Close the HTTP client."""
        self.client.close()


def create_mock_response(query: str) -> Dict[str, Any]:
    """
    Create a mock response for development mode.
    This will be replaced with actual DCL responses once test data is uploaded.
    """
    return {
        "status": "mock",
        "message": "DCLv2 not connected - showing mock response",
        "query": query,
        "entities": [],
        "metadata": {
            "source": "mock",
            "timestamp": None
        }
    }
