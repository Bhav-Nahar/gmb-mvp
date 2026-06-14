from typing import Dict, Any, Optional
from app.models.post import Post
from app.models.post_variant import PostVariant

class GBPPostMapper:
    @staticmethod
    def to_gbp_payload(post: Post, variant: Optional[PostVariant] = None) -> Dict[str, Any]:
        """
        Maps the canonical Post and optionally a PostVariant to the standard GBP LocalPost payload.
        
        Before building GBP payload:
        * fetch PostVariant for target location
        Use:
        * rendered_summary
        * rendered_cta_url
        NOT canonical Post fields directly (except as fallback if variant is missing).
        """
        # 1. Resolve text summary and CTA url from variant (with canonical fallback)
        summary = variant.rendered_summary if (variant and variant.rendered_summary) else post.summary
        cta_url = variant.rendered_cta_url if (variant and variant.rendered_cta_url) else post.cta_url

        # 2. Build base payload
        # Map internal post_type to GBP topicType
        # UPDATE -> STANDARD, EVENT -> EVENT, OFFER -> OFFER
        topic_type_map = {
            "UPDATE": "STANDARD",
            "EVENT": "EVENT",
            "OFFER": "OFFER"
        }
        mapped_topic_type = topic_type_map.get(post.post_type.upper() if post.post_type else "UPDATE", "STANDARD")

        payload = {
            "languageCode": post.language_code or "en-US",
            "summary": summary,
            "topicType": mapped_topic_type
        }

        # 3. Add Call to Action if specified
        if post.cta_type:
            cta_type_value = post.cta_type
            action_map = {
                "BOOK": "BOOK",
                "ORDER": "ORDER",
                "SHOP": "SHOP",
                "LEARN_MORE": "LEARN_MORE",
                "SIGN_UP": "SIGN_UP",
                "CALL": "CALL"
            }
            mapped_action = action_map.get(cta_type_value.upper(), "LEARN_MORE")
            
            payload["callToAction"] = {
                "actionType": mapped_action
            }
            if mapped_action != "CALL":
                if not cta_url:
                    raise ValueError(f"cta_url is required for CTA type {mapped_action}")
                payload["callToAction"]["url"] = str(cta_url)

        # 4. Add Media URL if present
        valid_media = [
            m for m in post.media
            if not m.is_deleted
            and (m.upload_status or "").upper() != "DELETED"
            and m.validation_status and m.validation_status.upper() == "VALID"
            and m.optimized_url
        ]
        
        if valid_media:
            media_items = []
            for m in valid_media[:1]:
                if "localhost" in m.optimized_url or "127.0.0.1" in m.optimized_url:
                    import logging
                    logging.warning(f"Media {m.id} has localhost URL {m.optimized_url}. Google API cannot fetch this. Omitting media from payload for local testing.")
                    continue
                media_items.append({
                    "mediaFormat": m.media_type or "PHOTO",
                    "sourceUrl": m.optimized_url
                })
            
            if media_items:
                payload["media"] = media_items

        return payload
