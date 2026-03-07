"""
Automated Gemini Image Generation Workflow
==========================================
Generates images for all VK Max Cleanz service prompts using
Google's Imagen 3 API (imagen-3.0-generate-002).

Usage:
    pip install google-genai Pillow
    python "gemini image generation.py"

Features:
    - Batch generates images for all 66 services
    - Saves with sanitized service names as filenames
    - Skips already-generated images (resume support)
    - Exponential backoff retry on rate-limit errors
    - Progress logging with success/failure summary
"""

import os
import re
import time
import base64
from io import BytesIO

from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image

# Load environment variables from .env file
load_dotenv()

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable is not set. "
                     "Create a .env file with GEMINI_API_KEY=your_key")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generated_images")
MODEL_NAME = "imagen-4.0-generate-001"
ASPECT_RATIO = "16:9"
DELAY_BETWEEN_REQUESTS = 10   # seconds between each API call
MAX_RETRIES = 5               # max retries on rate-limit / transient errors
INITIAL_BACKOFF = 15          # initial backoff in seconds for retries

# ─────────────────────────────────────────────
# SERVICE PROMPTS DATA
# ─────────────────────────────────────────────

SERVICES = {
    "description": "All images required for the VK Max Furnitures page redesign. Images should be placed in public/images/furniture/",
    "base_path": "/Users/satyalasujithcharles/react projects/vkmaxcleanz/public/images/furniture/",
    "hero_and_module_covers": [
        {
            "id": "hero_1",
            "name": "Hero Background",
            "filename": "hero_bg.png",
            "image_prompt": "Luxury modern living room interior with dark charcoal walls, a plush velvet sofa in warm tan, designer pendant light, polished concrete floor, minimalist style, moody ambient lighting, editorial interior photography, 16:9 wide aspect ratio, high resolution"
        },
        {
            "id": "hero_2",
            "name": "Hero Featured Chair",
            "filename": "hero_chair.png",
            "image_prompt": "Elegant modern accent chair in warm cognac leather on a white background, studio lighting, floating perspective with subtle shadow, product photography style, clean cut-out, 1:1 aspect ratio, premium luxury feel"
        },
        {
            "id": "cover_about",
            "name": "About / Story Section Cover",
            "filename": "about_cover.png",
            "image_prompt": "Craftsman carefully hand-polishing a wooden furniture piece in a warm-lit workshop, Indian artisan, sawdust in air, golden hour light filtering through windows, documentary photography style, 16:9 aspect ratio"
        },
        {
            "id": "cover_project_1",
            "name": "Project Showcase 1 - Home Interior",
            "filename": "project_home.png",
            "image_prompt": "Beautifully designed modern Indian home living room with custom wooden furniture, warm earthy tones, sofa set with coffee table, indoor plants, warm ambient lighting, interior design magazine style, 4:3 aspect ratio"
        },
        {
            "id": "cover_project_2",
            "name": "Project Showcase 2 - Luxury Office",
            "filename": "project_office.png",
            "image_prompt": "Premium corporate office interior with elegant wooden executive desk, leather chair, bookshelves, modern Indian office design, warm lighting, architectural photography style, 4:3 aspect ratio"
        },
        {
            "id": "cover_project_3",
            "name": "Project Showcase 3 - Cozy Café",
            "filename": "project_cafe.png",
            "image_prompt": "Stylish modern café interior with custom wooden tables and chairs, exposed brick wall, pendant lights, warm inviting atmosphere, Indian café design, lifestyle photography, 4:3 aspect ratio"
        },
        {
            "id": "cover_project_4",
            "name": "Project Showcase 4 - Custom Home",
            "filename": "project_custom.png",
            "image_prompt": "Luxury custom-furnished master bedroom with premium wooden bed frame, matching nightstands, soft warm lighting, earthy color palette, modern Indian home interior, editorial photography, 4:3 aspect ratio"
        }
    ],
    "category_covers": [
        {
            "id": "cat_living",
            "name": "Living Room Category",
            "filename": "cat_living_room.png",
            "image_prompt": "Modern living room vignette with designer sofa, coffee table and floor lamp, warm neutral tones, soft lighting, minimalist interior, editorial style on clean background, 3:4 portrait aspect ratio"
        },
        {
            "id": "cat_bedroom",
            "name": "Bedroom Category",
            "filename": "cat_bedroom.png",
            "image_prompt": "Elegant modern bedroom with upholstered bed frame, nightstand and soft bedding, muted earth tones, cozy ambient light, minimalist interior photography, 3:4 portrait aspect ratio"
        },
        {
            "id": "cat_dining",
            "name": "Dining Room Category",
            "filename": "cat_dining.png",
            "image_prompt": "Stylish dining room with solid wooden dining table and chairs, pendant light above, warm setting with tableware, modern Indian home interior, 3:4 portrait aspect ratio"
        },
        {
            "id": "cat_office",
            "name": "Home Office Category",
            "filename": "cat_office.png",
            "image_prompt": "Modern home office setup with sleek wooden desk, ergonomic chair, monitor stand, bookshelves, warm natural light, productivity workspace aesthetic, 3:4 portrait aspect ratio"
        },
        {
            "id": "cat_outdoor",
            "name": "Outdoor Category",
            "filename": "cat_outdoor.png",
            "image_prompt": "Beautiful outdoor patio furniture set on a terrace, teak wood table and chairs with cushions, green plants, warm evening light, Indian rooftop garden setting, 3:4 portrait aspect ratio"
        },
        {
            "id": "cat_storage",
            "name": "Storage Category",
            "filename": "cat_storage.png",
            "image_prompt": "Modern wooden storage unit with open shelving and closed cabinets, books and decor items displayed, clean minimalist room setting, warm tones, 3:4 portrait aspect ratio"
        }
    ],
    "products": [
        {
            "id": 1,
            "product_name": "Velvet Curve Sofa",
            "category": "Living Room",
            "subcategory": "Sofas",
            "price": 42999,
            "filename": "prod_velvet_curve_sofa.png",
            "image_prompt": "Modern curved 3-seater sofa in olive green velvet fabric, wooden legs, clean white studio background, product photography with soft shadows, 4:3 aspect ratio"
        },
        {
            "id": 2,
            "product_name": "Cognac Leather Armchair",
            "category": "Living Room",
            "subcategory": "Accent Chairs",
            "price": 18999,
            "filename": "prod_cognac_armchair.png",
            "image_prompt": "Mid-century modern accent armchair in cognac brown leather with wooden frame, clean white studio background, product photography with soft shadows, 4:3 aspect ratio"
        },
        {
            "id": 3,
            "product_name": "Marble Top Coffee Table",
            "category": "Living Room",
            "subcategory": "Coffee Tables",
            "price": 14999,
            "filename": "prod_marble_coffee_table.png",
            "image_prompt": "Modern coffee table with white marble top and black metal geometric base, clean white studio background, product photography with soft shadows, 4:3 aspect ratio"
        },
        {
            "id": 4,
            "product_name": "Walnut TV Console",
            "category": "Living Room",
            "subcategory": "TV Units",
            "price": 22999,
            "filename": "prod_walnut_tv_console.png",
            "image_prompt": "Mid-century walnut wood TV console with sliding doors and open shelving, clean white studio background, product photography with soft shadows, 4:3 aspect ratio"
        },
        {
            "id": 5,
            "product_name": "Modular L-Shape Sofa",
            "category": "Living Room",
            "subcategory": "Sofas",
            "price": 67999,
            "filename": "prod_modular_l_sofa.png",
            "image_prompt": "Large modular L-shaped sofa in charcoal grey fabric with chaise lounge, modern design, clean white studio background, product photography with soft shadows, 4:3 aspect ratio"
        },
        {
            "id": 6,
            "product_name": "Rattan Accent Chair",
            "category": "Living Room",
            "subcategory": "Accent Chairs",
            "price": 12999,
            "filename": "prod_rattan_accent_chair.png",
            "image_prompt": "Natural rattan woven accent chair with cream cushion, bohemian style, clean white studio background, product photography with soft shadows, 4:3 aspect ratio"
        },
        {
            "id": 7,
            "product_name": "Nested Side Tables Set",
            "category": "Living Room",
            "subcategory": "Side Tables",
            "price": 8999,
            "filename": "prod_nested_side_tables.png",
            "image_prompt": "Set of two nesting round side tables with brass metal frame and black marble top, clean white studio background, product photography with soft shadows, 4:3 aspect ratio"
        },
        {
            "id": 8,
            "product_name": "Industrial Bookshelf",
            "category": "Living Room",
            "subcategory": "Shelving",
            "price": 16999,
            "filename": "prod_industrial_bookshelf.png",
            "image_prompt": "Tall industrial-style ladder bookshelf with black metal frame and wooden shelves, 5 tiers, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 9,
            "product_name": "Upholstered King Bed",
            "category": "Bedroom",
            "subcategory": "Beds",
            "price": 54999,
            "filename": "prod_upholstered_king_bed.png",
            "image_prompt": "Luxury upholstered king-size bed frame with tufted headboard in warm beige fabric, wooden legs, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 10,
            "product_name": "Platform Queen Bed",
            "category": "Bedroom",
            "subcategory": "Beds",
            "price": 38999,
            "filename": "prod_platform_queen_bed.png",
            "image_prompt": "Modern platform queen bed in solid walnut wood with minimalist floating design, built-in nightstand ledges, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 11,
            "product_name": "Bedside Table Set",
            "category": "Bedroom",
            "subcategory": "Nightstands",
            "price": 9999,
            "filename": "prod_bedside_table_set.png",
            "image_prompt": "Pair of modern wooden bedside tables with single drawer and open shelf, warm teak finish, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 12,
            "product_name": "Sliding Door Wardrobe",
            "category": "Bedroom",
            "subcategory": "Wardrobes",
            "price": 62999,
            "filename": "prod_sliding_wardrobe.png",
            "image_prompt": "Large modern 3-door sliding wardrobe in matte black and walnut wood combination, full-length mirror on center door, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 13,
            "product_name": "Dresser with Mirror",
            "category": "Bedroom",
            "subcategory": "Dressers",
            "price": 28999,
            "filename": "prod_dresser_mirror.png",
            "image_prompt": "Elegant 6-drawer dresser in white lacquer finish with brass handles and matching round wall mirror, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 14,
            "product_name": "Storage Ottoman Bench",
            "category": "Bedroom",
            "subcategory": "Benches",
            "price": 11999,
            "filename": "prod_storage_ottoman.png",
            "image_prompt": "Upholstered storage ottoman bench in dusty pink velvet with gold legs, rectangular shape, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 15,
            "product_name": "Wooden Clothes Rack",
            "category": "Bedroom",
            "subcategory": "Storage",
            "price": 6999,
            "filename": "prod_clothes_rack.png",
            "image_prompt": "Minimalist freestanding wooden clothes rack in natural oak with bottom shelf for shoes, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 16,
            "product_name": "Bunk Bed with Storage",
            "category": "Bedroom",
            "subcategory": "Beds",
            "price": 44999,
            "filename": "prod_bunk_bed.png",
            "image_prompt": "Modern children's bunk bed in solid pine wood with built-in storage drawers and ladder, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 17,
            "product_name": "6-Seater Dining Table",
            "category": "Dining Room",
            "subcategory": "Dining Tables",
            "price": 34999,
            "filename": "prod_6_seater_dining.png",
            "image_prompt": "Solid sheesham wood 6-seater dining table with clean rectangular top and tapered legs, warm natural wood finish, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 18,
            "product_name": "Upholstered Dining Chair",
            "category": "Dining Room",
            "subcategory": "Dining Chairs",
            "price": 5999,
            "filename": "prod_upholstered_dining_chair.png",
            "image_prompt": "Modern dining chair with upholstered grey fabric seat and curved wooden backrest, tapered legs, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 19,
            "product_name": "Round Dining Table",
            "category": "Dining Room",
            "subcategory": "Dining Tables",
            "price": 27999,
            "filename": "prod_round_dining_table.png",
            "image_prompt": "Modern round dining table with white marble top and black pedestal base, seats 4, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 20,
            "product_name": "Dining Bench",
            "category": "Dining Room",
            "subcategory": "Benches",
            "price": 12999,
            "filename": "prod_dining_bench.png",
            "image_prompt": "Long solid wood dining bench with simple minimalist design and warm honey finish, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 21,
            "product_name": "Crockery Cabinet",
            "category": "Dining Room",
            "subcategory": "Cabinets",
            "price": 38999,
            "filename": "prod_crockery_cabinet.png",
            "image_prompt": "Tall wooden crockery display cabinet with glass doors on top and closed storage below, warm walnut finish, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 22,
            "product_name": "Bar Cabinet",
            "category": "Dining Room",
            "subcategory": "Bar Units",
            "price": 24999,
            "filename": "prod_bar_cabinet.png",
            "image_prompt": "Art deco style bar cabinet in dark wood with brass accents, fold-down serving shelf, interior glass holder rack, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 23,
            "product_name": "Folding Dining Set",
            "category": "Dining Room",
            "subcategory": "Dining Sets",
            "price": 18999,
            "filename": "prod_folding_dining_set.png",
            "image_prompt": "Compact space-saving folding dining table with 4 folding chairs stored inside, light oak wood, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 24,
            "product_name": "Serving Trolley Cart",
            "category": "Dining Room",
            "subcategory": "Trolleys",
            "price": 8999,
            "filename": "prod_serving_trolley.png",
            "image_prompt": "Modern 2-tier serving trolley cart with black metal frame and wooden trays, on wheels, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 25,
            "product_name": "Executive Desk",
            "category": "Home Office",
            "subcategory": "Desks",
            "price": 29999,
            "filename": "prod_executive_desk.png",
            "image_prompt": "Large executive writing desk in dark walnut wood with 3 drawers, leather desk pad inlay, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 26,
            "product_name": "Ergonomic Mesh Chair",
            "category": "Home Office",
            "subcategory": "Office Chairs",
            "price": 15999,
            "filename": "prod_ergonomic_mesh_chair.png",
            "image_prompt": "High-back ergonomic office chair with breathable mesh back, adjustable armrests and headrest, black, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 27,
            "product_name": "Standing Desk",
            "category": "Home Office",
            "subcategory": "Desks",
            "price": 34999,
            "filename": "prod_standing_desk.png",
            "image_prompt": "Modern electric height-adjustable standing desk with walnut wood top and black metal frame, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 28,
            "product_name": "Office Bookcase",
            "category": "Home Office",
            "subcategory": "Shelving",
            "price": 19999,
            "filename": "prod_office_bookcase.png",
            "image_prompt": "Professional wooden bookcase with 4 shelves and lower cabinet doors, warm oak finish, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 29,
            "product_name": "Filing Cabinet",
            "category": "Home Office",
            "subcategory": "Storage",
            "price": 10999,
            "filename": "prod_filing_cabinet.png",
            "image_prompt": "Modern 3-drawer filing cabinet in matte white with wooden top surface and brass handles, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 30,
            "product_name": "Monitor Stand Shelf",
            "category": "Home Office",
            "subcategory": "Accessories",
            "price": 3999,
            "filename": "prod_monitor_stand.png",
            "image_prompt": "Bamboo wood monitor riser stand with storage compartments underneath, minimalist design, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 31,
            "product_name": "Study Table for Kids",
            "category": "Home Office",
            "subcategory": "Desks",
            "price": 12999,
            "filename": "prod_kids_study_table.png",
            "image_prompt": "Colorful height-adjustable children's study desk in white and light blue with built-in book shelf and pencil holder, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 32,
            "product_name": "Corner Desk",
            "category": "Home Office",
            "subcategory": "Desks",
            "price": 18999,
            "filename": "prod_corner_desk.png",
            "image_prompt": "L-shaped corner computer desk in white with metal legs, built-in cable management and shelving unit, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 33,
            "product_name": "Garden Swing Chair",
            "category": "Outdoor",
            "subcategory": "Swing & Hammocks",
            "price": 21999,
            "filename": "prod_garden_swing.png",
            "image_prompt": "Stylish macrame hanging swing chair in natural cotton with wooden spreader bar and cream cushion, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 34,
            "product_name": "Teak Patio Set",
            "category": "Outdoor",
            "subcategory": "Outdoor Dining",
            "price": 48999,
            "filename": "prod_teak_patio_set.png",
            "image_prompt": "Premium teak wood outdoor dining set with round table and 4 folding chairs, natural golden teak finish, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 35,
            "product_name": "Planter Stand Set",
            "category": "Outdoor",
            "subcategory": "Planters",
            "price": 4999,
            "filename": "prod_planter_stands.png",
            "image_prompt": "Set of 3 modern metal plant stands in black at different heights, minimalist geometric design, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 36,
            "product_name": "Outdoor Lounge Chair",
            "category": "Outdoor",
            "subcategory": "Loungers",
            "price": 15999,
            "filename": "prod_outdoor_lounger.png",
            "image_prompt": "Modern outdoor reclining lounge chair in weather-resistant teak wood with white cushion pad, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 37,
            "product_name": "Balcony Bistro Set",
            "category": "Outdoor",
            "subcategory": "Bistro Sets",
            "price": 9999,
            "filename": "prod_balcony_bistro.png",
            "image_prompt": "Compact 2-person bistro table and chairs set in powder-coated black metal, suitable for small balcony, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 38,
            "product_name": "Garden Bench",
            "category": "Outdoor",
            "subcategory": "Benches",
            "price": 13999,
            "filename": "prod_garden_bench.png",
            "image_prompt": "Traditional wrought iron and wooden garden bench with curved armrests, teak wood seat, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 39,
            "product_name": "Shoe Rack Tower",
            "category": "Storage",
            "subcategory": "Shoe Storage",
            "price": 7999,
            "filename": "prod_shoe_rack.png",
            "image_prompt": "Tall narrow 6-tier wooden shoe rack in oak finish with slatted shelves, holds 18 pairs, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 40,
            "product_name": "Entryway Console",
            "category": "Storage",
            "subcategory": "Console Tables",
            "price": 16999,
            "filename": "prod_entryway_console.png",
            "image_prompt": "Slim entryway console table in dark walnut with 2 drawers and lower shelf, minimalist design, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 41,
            "product_name": "Wall-Mounted Shelf Unit",
            "category": "Storage",
            "subcategory": "Wall Shelves",
            "price": 5999,
            "filename": "prod_wall_shelf_unit.png",
            "image_prompt": "Set of 3 floating wall-mounted wooden shelves in walnut finish, different lengths, with hidden brackets, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 42,
            "product_name": "Cube Storage Organizer",
            "category": "Storage",
            "subcategory": "Organizers",
            "price": 10999,
            "filename": "prod_cube_organizer.png",
            "image_prompt": "Modern 9-cube wooden storage organizer unit in white with some fabric baskets inserted, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 43,
            "product_name": "Hallway Coat Rack",
            "category": "Storage",
            "subcategory": "Racks",
            "price": 4499,
            "filename": "prod_coat_rack.png",
            "image_prompt": "Modern freestanding wooden coat rack tree with multiple hooks and small base shelf, light bamboo finish, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 44,
            "product_name": "Multipurpose Cabinet",
            "category": "Storage",
            "subcategory": "Cabinets",
            "price": 21999,
            "filename": "prod_multipurpose_cabinet.png",
            "image_prompt": "Versatile multipurpose storage cabinet with adjustable shelves, 2 glass doors on top, 2 wooden doors below, teak finish, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 45,
            "product_name": "Under-bed Storage Drawers",
            "category": "Storage",
            "subcategory": "Under-bed",
            "price": 6499,
            "filename": "prod_underbed_drawers.png",
            "image_prompt": "Set of 2 rolling under-bed storage drawers in natural pine wood with fabric lining, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 46,
            "product_name": "Floor Lamp with Shelf",
            "category": "Living Room",
            "subcategory": "Lighting",
            "price": 7999,
            "filename": "prod_floor_lamp_shelf.png",
            "image_prompt": "Modern floor lamp with built-in wooden shelves, black metal frame with warm light fabric shade on top, 3 wooden tiers, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 47,
            "product_name": "Pouf Ottoman",
            "category": "Living Room",
            "subcategory": "Ottomans",
            "price": 3999,
            "filename": "prod_pouf_ottoman.png",
            "image_prompt": "Round knitted pouf ottoman in mustard yellow cotton yarn, dense comfortable seating, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 48,
            "product_name": "Media Console Unit",
            "category": "Living Room",
            "subcategory": "TV Units",
            "price": 26999,
            "filename": "prod_media_console.png",
            "image_prompt": "Modern media console entertainment unit in matte black and walnut wood combination, with open and closed compartments, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 49,
            "product_name": "Scandinavian Dining Set",
            "category": "Dining Room",
            "subcategory": "Dining Sets",
            "price": 42999,
            "filename": "prod_scandinavian_dining.png",
            "image_prompt": "Complete 4-seater Scandinavian dining set with round white table and light oak wood legs, matching wooden chairs, clean white studio background, product photography, 4:3 aspect ratio"
        },
        {
            "id": 50,
            "product_name": "Vanity Dressing Table",
            "category": "Bedroom",
            "subcategory": "Dressers",
            "price": 19999,
            "filename": "prod_vanity_table.png",
            "image_prompt": "Modern vanity dressing table in white with round LED-lit mirror, 2 drawers, matching upholstered stool, clean white studio background, product photography, 4:3 aspect ratio"
        }
    ]
}



# ─────────────────────────────────────────────
# UTILITY FUNCTIONS
# ─────────────────────────────────────────────

def sanitize_filename(name: str) -> str:
    """Convert service name to a safe filename."""
    # Replace special characters with readable alternatives
    name = name.replace("&", "and")
    name = name.replace("/", "-")
    # Remove characters that aren't alphanumeric, spaces, hyphens, or parentheses
    name = re.sub(r"[^\w\s\-\(\)]", "", name)
    # Collapse multiple spaces/hyphens
    name = re.sub(r"\s+", "_", name.strip())
    name = re.sub(r"_+", "_", name)
    return name


def get_item_name(item: dict) -> str:
    """Get the display name from an item (handles both 'name' and 'product_name' keys)."""
    return item.get("product_name", item.get("name", "Unknown"))


def gather_all_items() -> list:
    """
    Flatten all items from the nested SERVICES dictionary into a single list.
    Each item gets a 'display_name' field added for convenience.
    """
    all_items = []
    for section_key in ["hero_and_module_covers", "category_covers", "products"]:
        for item in SERVICES.get(section_key, []):
            item["display_name"] = get_item_name(item)
            all_items.append(item)
    return all_items


def generate_single_image(client, item: dict, output_dir: str) -> bool:
    """
    Generate and save one image for an item.
    Returns True on success, False on failure.
    """
    display_name = item["display_name"]
    prompt = item["image_prompt"]
    filename = item["filename"]
    filepath = os.path.join(output_dir, filename)

    # Skip if already exists (resume support)
    if os.path.exists(filepath):
        print(f"  ⏭  Already exists: {filename}")
        return True

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_images(
                model=MODEL_NAME,
                prompt=prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio=ASPECT_RATIO,
                ),
            )

            # Check if we got images back
            if response.generated_images and len(response.generated_images) > 0:
                image_data = response.generated_images[0].image
                # image_data has .image_bytes property
                img = Image.open(BytesIO(image_data.image_bytes))
                img.save(filepath, "PNG")
                print(f"  ✅ Saved: {filename}")
                return True
            else:
                print(f"  ⚠️  No image returned for: {display_name}")
                return False

        except Exception as e:
            error_msg = str(e)

            # Rate limit / quota error — retry with backoff
            if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg or "quota" in error_msg.lower():
                backoff = INITIAL_BACKOFF * (2 ** (attempt - 1))
                print(f"  ⏳ Rate limited (attempt {attempt}/{MAX_RETRIES}). "
                      f"Waiting {backoff}s...")
                time.sleep(backoff)
                continue

            # Other transient errors — retry
            if attempt < MAX_RETRIES and ("500" in error_msg or "503" in error_msg):
                backoff = INITIAL_BACKOFF * attempt
                print(f"  🔄 Server error (attempt {attempt}/{MAX_RETRIES}). "
                      f"Retrying in {backoff}s...")
                time.sleep(backoff)
                continue

            # Non-retryable error
            print(f"  ❌ Failed: {display_name}")
            print(f"     Error: {error_msg}")
            return False

    print(f"  ❌ Max retries exceeded for: {display_name}")
    return False


# ─────────────────────────────────────────────
# MAIN WORKFLOW
# ─────────────────────────────────────────────

def main():
    # Gather all items from the nested structure
    all_items = gather_all_items()
    output_dir = SERVICES.get("base_path", OUTPUT_DIR)

    print("=" * 60)
    print("🎨 VK Max Furnitures — Automated Image Generation")
    print("=" * 60)
    print(f"  Model     : {MODEL_NAME}")
    print(f"  Items     : {len(all_items)}")
    print(f"  Output    : {output_dir}")
    print(f"  Delay     : {DELAY_BETWEEN_REQUESTS}s between requests")
    print("=" * 60)
    print()

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    # Initialize Gemini client
    print("🔑 Initializing Gemini API client...")
    client = genai.Client(api_key=GEMINI_API_KEY)
    print("   Client ready!\n")

    # Track results
    success_count = 0
    fail_count = 0
    skipped_count = 0
    failed_items = []

    total = len(all_items)
    start_time = time.time()

    for i, item in enumerate(all_items, 1):
        display_name = item["display_name"]
        filename = item["filename"]
        filepath = os.path.join(output_dir, filename)

        print(f"[{i:02d}/{total}] {display_name}")

        # Check if already exists
        if os.path.exists(filepath):
            print(f"  ⏭  Already exists — skipping\n")
            skipped_count += 1
            success_count += 1
            continue

        # Generate image
        result = generate_single_image(client, item, output_dir)

        if result:
            success_count += 1
        else:
            fail_count += 1
            failed_items.append(display_name)

        # Delay before next request (except after the last one)
        if i < total:
            print(f"  ⏱  Waiting {DELAY_BETWEEN_REQUESTS}s before next request...\n")
            time.sleep(DELAY_BETWEEN_REQUESTS)

    # ─── Summary ───
    elapsed = time.time() - start_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)

    print()
    print("=" * 60)
    print("📊 GENERATION SUMMARY")
    print("=" * 60)
    print(f"  ✅ Successful : {success_count}/{total}")
    print(f"  ⏭  Skipped    : {skipped_count}")
    print(f"  ❌ Failed     : {fail_count}/{total}")
    print(f"  ⏱  Time       : {minutes}m {seconds}s")
    print(f"  📁 Output     : {output_dir}")

    if failed_items:
        print()
        print("  Failed items:")
        for name in failed_items:
            print(f"    • {name}")

    print("=" * 60)
    print()

    if fail_count == 0:
        print("🎉 All images generated successfully!")
    else:
        print(f"⚠️  {fail_count} image(s) failed. Re-run the script to retry "
              f"(already-generated images will be skipped).")


if __name__ == "__main__":
    main()