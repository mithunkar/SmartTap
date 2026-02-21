"""
Keyword-based matching utilities for variable and crop identification
Used as fallback when LLM parsing is uncertain or for validation
"""

import json
import os
from typing import Dict, List, Tuple, Optional

class KeywordMatcher:
    """Matches user queries to OpenET variables and crop names using keyword mappings"""
    
    def __init__(self):
        """Load keyword mappings from JSON files"""
        base_path = os.path.dirname(os.path.dirname(__file__))
        
        var_path = os.path.join(base_path, "data", "openet_variable_keywords.json")
        crop_path = os.path.join(base_path, "data", "crop_name_keywords.json")
        
        self.variable_keywords = {}
        self.crop_keywords = {}
        
        try:
            with open(var_path, 'r') as f:
                self.variable_keywords = json.load(f)
        except FileNotFoundError:
            print(f"Warning: Variable keywords file not found at {var_path}")
        
        try:
            with open(crop_path, 'r') as f:
                self.crop_keywords = json.load(f)
        except FileNotFoundError:
            print(f"Warning: Crop keywords file not found at {crop_path}")
    
    def normalize_query(self, query: str) -> List[str]:
        """Normalize query to lowercase tokens"""
        # Remove punctuation and split
        import re
        query = query.lower()
        query = re.sub(r'[^\w\s]', ' ', query)
        tokens = query.split()
        return tokens
    
    def match_variable(self, query: str, top_k: int = 3) -> List[Tuple[str, float, Dict]]:
        """
        Match query to OpenET variables using keyword overlap
        
        Args:
            query: User query string
            top_k: Number of top matches to return
            
        Returns:
            List of tuples: (variable_name, score, variable_info)
        """
        tokens = self.normalize_query(query)
        scores = {}
        
        for var_name, var_info in self.variable_keywords.items():
            score = 0
            keywords = [kw.lower() for kw in var_info.get("keywords", [])]
            
            # Exact phrase matching (higher weight)
            for keyword in keywords:
                if keyword in query.lower():
                    score += 2.0
            
            # Token-level matching
            for keyword in keywords:
                kw_tokens = keyword.split()
                for kw_token in kw_tokens:
                    if kw_token in tokens:
                        score += 1.0
            
            # Bonus for matching related concepts
            related = [r.lower() for r in var_info.get("related_concepts", [])]
            for concept in related:
                if concept in query.lower():
                    score += 0.5
            
            if score > 0:
                scores[var_name] = (score, var_info)
        
        # Sort by score descending
        ranked = sorted(scores.items(), key=lambda x: x[1][0], reverse=True)
        
        # Return top_k results with normalized scores
        results = []
        if ranked:
            max_score = ranked[0][1][0]
            for var_name, (score, var_info) in ranked[:top_k]:
                normalized_score = score / max_score if max_score > 0 else 0
                results.append((var_name, normalized_score, var_info))
        
        return results
    
    def match_crop(self, query: str, top_k: int = 5) -> List[Tuple[int, str, float, Dict]]:
        """
        Match query to crop names using keyword overlap
        
        Args:
            query: User query string
            top_k: Number of top matches to return
            
        Returns:
            List of tuples: (cdl_code, crop_name, score, crop_info)
        """
        tokens = self.normalize_query(query)
        scores = {}
        
        if not self.crop_keywords or "crop_groups" not in self.crop_keywords:
            return []
        
        for group_name, group_info in self.crop_keywords["crop_groups"].items():
            crops = group_info.get("crops", {})
            
            for cdl_str, crop_info in crops.items():
                cdl_code = int(cdl_str) if cdl_str.isdigit() else crop_info.get("cdl_code")
                crop_name = crop_info.get("crop_name", "")
                score = 0
                
                # Match crop name directly
                if crop_name.lower() in query.lower():
                    score += 5.0
                
                # Match keywords
                keywords = [kw.lower() for kw in crop_info.get("keywords", [])]
                for keyword in keywords:
                    if keyword in query.lower():
                        score += 3.0
                
                # Match synonyms
                synonyms = [s.lower() for s in crop_info.get("synonyms", [])]
                for synonym in synonyms:
                    if synonym in query.lower():
                        score += 2.0
                
                # Match group keywords
                group_keywords = [kw.lower() for kw in group_info.get("keywords", [])]
                for group_kw in group_keywords:
                    if group_kw in query.lower():
                        score += 0.5
                
                if score > 0:
                    scores[cdl_code] = (crop_name, score, crop_info)
        
        # Sort by score descending
        ranked = sorted(scores.items(), key=lambda x: x[1][1], reverse=True)
        
        # Return top_k results with normalized scores
        results = []
        if ranked:
            max_score = ranked[0][1][1]
            for cdl_code, (crop_name, score, crop_info) in ranked[:top_k]:
                normalized_score = score / max_score if max_score > 0 else 0
                results.append((cdl_code, crop_name, normalized_score, crop_info))
        
        return results
    
    def match_query(self, query: str) -> Dict:
        """
        Full query matching for both variables and crops
        
        Args:
            query: User query string
            
        Returns:
            Dictionary with top variable and crop matches
        """
        variable_matches = self.match_variable(query, top_k=3)
        crop_matches = self.match_crop(query, top_k=5)
        
        result = {
            "query": query,
            "variables": [
                {
                    "variable": var_name,
                    "description": var_info.get("variable_name", ""),
                    "score": score,
                    "confidence": "high" if score > 0.7 else "medium" if score > 0.4 else "low"
                }
                for var_name, score, var_info in variable_matches
            ],
            "crops": [
                {
                    "cdl_code": cdl_code,
                    "crop_name": crop_name,
                    "score": score,
                    "confidence": "high" if score > 0.7 else "medium" if score > 0.4 else "low"
                }
                for cdl_code, crop_name, score, crop_info in crop_matches
            ]
        }
        
        return result


# Convenience functions for backward compatibility
def match_variable_keywords(query: str) -> Optional[str]:
    """Simple variable matching returning only the top match"""
    matcher = KeywordMatcher()
    matches = matcher.match_variable(query, top_k=1)
    if matches and matches[0][1] > 0.3:  # Min threshold
        return matches[0][0]
    return None


def match_crop_keywords(query: str) -> Optional[Tuple[int, str]]:
    """Simple crop matching returning only the top match"""
    matcher = KeywordMatcher()
    matches = matcher.match_crop(query, top_k=1)
    if matches and matches[0][2] > 0.3:  # Min threshold
        return (matches[0][0], matches[0][1])
    return None


if __name__ == "__main__":
    # Test the matcher
    matcher = KeywordMatcher()
    
    test_queries = [
        "How much water did crops use?",
        "Show me winter wheat fields",
        "What's the irrigation requirement for alfalfa?",
        "Rainfall in Hood River",
        "Cherry orchard water consumption"
    ]
    
    for query in test_queries:
        print(f"\nQuery: {query}")
        result = matcher.match_query(query)
        
        print("Top Variables:")
        for v in result["variables"][:2]:
            print(f"  - {v['variable']} ({v['description']}): {v['score']:.2f} ({v['confidence']})")
        
        print("Top Crops:")
        for c in result["crops"][:2]:
            print(f"  - {c['crop_name']} (CDL {c['cdl_code']}): {c['score']:.2f} ({c['confidence']})")
