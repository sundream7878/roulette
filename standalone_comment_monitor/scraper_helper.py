    def _deduplicate_by_id(self, comments: List[CommentData]) -> List[CommentData]:
        """comment_id 기반 중복 제거"""
        seen_ids = set()
        unique = []
        
        for comment in comments:
            comment_id = comment.get('comment_id', '')
            if comment_id and comment_id not in seen_ids:
                seen_ids.add(comment_id)
                unique.append(comment)
        
        return unique
