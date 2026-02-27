"""
Test Script for Image Indexing

Demonstrates image captioning and indexing with the ImageIndexer.

Usage:
    # Test with a local image
    python scripts/test_image_indexing.py --image data/docs/diagram.png

    # Test with an image URL
    python scripts/test_image_indexing.py --image https://example.com/chart.jpg

    # Index all images in a directory
    python scripts/test_image_indexing.py --directory data/docs/
"""

import sys
import argparse
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "backend"))

from tools.doc_search import ImageIndexer, RagTool


def caption_single_image(image_path: str):
    """Test captioning a single image."""
    print(f"🖼️  Captioning image: {image_path}")

    indexer = ImageIndexer()

    try:
        chunks = indexer.ingest(image_path)
        if chunks:
            chunk = chunks[0]
            print("\n✓ Caption generated:")
            print(f"  {chunk.content}")
            print(f"\n  Metadata:")
            for key, value in chunk.metadata.items():
                if key not in ["chunk_id", "caption"]:
                    print(f"    {key}: {value}")
            return True
        else:
            print("✗ No caption generated")
            return False

    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def index_images_directory(directory: str, index_name: str = "test_images"):
    """Index all images in a directory."""
    print(f"📁 Indexing images in: {directory}")

    rag = RagTool(index_name=index_name)

    dir_path = Path(directory)
    if not dir_path.exists():
        print(f"✗ Directory not found: {directory}")
        return False

    # Find all images
    image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".webp"}
    images = [
        f for f in dir_path.rglob("*")
        if f.suffix.lower() in image_extensions
    ]

    print(f"Found {len(images)} images")

    if not images:
        print("No images found in directory")
        return True

    # Index each image
    success_count = 0
    for i, img_path in enumerate(images, 1):
        print(f"\n[{i}/{len(images)}] {img_path.name}")
        try:
            added = rag.ingest_file(str(img_path))
            if added > 0:
                success_count += 1
                print(f"  ✓ Indexed ({added} chunk)")
            else:
                print(f"  ✗ Failed")
        except Exception as e:
            print(f"  ✗ Error: {e}")

    # Save index
    rag.vector_store.save()

    # Show stats
    stats = rag.get_stats()
    print(f"\n📊 Final Stats:")
    print(f"  Successfully indexed: {success_count}/{len(images)}")
    print(f"  Total chunks in index: {stats['total_chunks']}")
    print(f"  Source types: {stats['source_types']}")

    return success_count > 0


def search_images(query: str, index_name: str = "test_images"):
    """Search indexed images."""
    print(f"🔍 Searching for: {query}")

    rag = RagTool(index_name=index_name)

    if not rag.vector_store.is_ready:
        print("✗ Index not ready. Please index images first.")
        return False

    results = rag.search(query, top_k=5, source_type="image")

    if not results:
        print("No results found")
        return False

    print(f"\nFound {len(results)} results:\n")
    for i, result in enumerate(results, 1):
        chunk = result.chunk
        source_name = Path(chunk.source).name
        print(f"[{i}] {source_name}")
        print(f"    Score: {result.score:.4f}")
        print(f"    Caption: {chunk.metadata.get('caption', 'N/A')[:100]}...")
        print()

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Test image indexing and captioning",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("--image", help="Path or URL to image")
    parser.add_argument("--directory", help="Directory containing images")
    parser.add_argument("--search", help="Search query for indexed images")
    parser.add_argument("--index-name", default="test_images", help="Index name")
    parser.add_argument("--vision-model", default=None, help="Vision model (default: llava)")

    args = parser.parse_args()

    if args.image:
        # Caption single image
        if args.vision_model:
            indexer = ImageIndexer(vision_model=args.vision_model)
        else:
            indexer = ImageIndexer()

        chunks = indexer.ingest(args.image)
        if chunks:
            print("\n" + "="*50)
            print(chunks[0].content)
        return

    if args.directory:
        # Index directory
        success = index_images_directory(args.directory, args.index_name)
        sys.exit(0 if success else 1)
        return

    if args.search:
        # Search images
        success = search_images(args.search, args.index_name)
        sys.exit(0 if success else 1)
        return

    # Default: show help
    parser.print_help()


if __name__ == "__main__":
    main()
