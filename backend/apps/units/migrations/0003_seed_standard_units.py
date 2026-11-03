from django.db import migrations


def seed_units(apps, schema_editor):
    UnitType = apps.get_model("units", "UnitType")

    STANDARD_UNITS = [
        {
            "code": "infantry",
            "name": "Lính Bộ Binh Cơ Bản",
            "category": "UNIT",
            "description": "Đơn vị chiến đấu cơ bản giá rẻ, tạo áp lực liên tục lên các làn đường.",
            "cost": 15,
            "is_starter": True,
            "is_unlockable": False,
            "is_active": True,
            "base_stats": {
                "hp": 40,
                "damage": 10,
                "range": 1,
                "movement": 1,
                "strategic_role": "Tạo áp lực ban đầu và dọn đường.",
            },
        },
        {
            "code": "mg_tower",
            "name": "Tháp Súng Máy",
            "category": "TOWER",
            "description": "Công sự phòng thủ tầm trung hiệu quả cao trước các đơn vị lính nhẹ.",
            "cost": 25,
            "is_starter": True,
            "is_unlockable": False,
            "is_active": True,
            "base_stats": {
                "hp": 100,
                "damage": 15,
                "range": 2,
                "movement": 0,
                "strategic_role": "Phòng thủ tuyến đầu tiêu diệt bộ binh.",
            },
        },
        {
            "code": "tank",
            "name": "Xe Tăng Thiết Giáp",
            "category": "UNIT",
            "description": "Đơn vị bọc thép hạng nặng chịu đòn tốt nhất, bảo vệ các đơn vị yếu máu phía sau.",
            "cost": 35,
            "is_starter": False,
            "is_unlockable": True,
            "is_active": True,
            "base_stats": {
                "hp": 120,
                "damage": 25,
                "range": 1,
                "movement": 1,
                "strategic_role": "Che chắn sát thương cho hỏa lực phía sau và phá công sự.",
            },
        },
        {
            "code": "artillery",
            "name": "Pháo Binh Tầm Xa",
            "category": "UNIT",
            "description": "Hỏa lực pháo kích tầm xa cực mạnh, có khả năng bắn phá từ khoảng cách 3 node.",
            "cost": 45,
            "is_starter": False,
            "is_unlockable": True,
            "is_active": True,
            "base_stats": {
                "hp": 45,
                "damage": 40,
                "range": 3,
                "movement": 1,
                "strategic_role": "Tấn công từ tuyến sau tiêu diệt công sự và căn cứ đối phương.",
            },
        },
        {
            "code": "cannon_tower",
            "name": "Tháp Đại Bác Phá Giáp",
            "category": "TOWER",
            "description": "Tháp phòng thủ hạng nặng với sát thương 30/round và tầm bắn lên tới 3 node.",
            "cost": 40,
            "is_starter": False,
            "is_unlockable": True,
            "is_active": True,
            "base_stats": {
                "hp": 150,
                "damage": 30,
                "range": 3,
                "movement": 0,
                "strategic_role": "Khắc chế triệt để xe tăng và hỏa lực hạng nặng của địch.",
            },
        },
        {
            "code": "shield_generator",
            "name": "Máy Tạo Khiên Căn Cứ",
            "category": "TOWER",
            "description": "Thiết bị bảo vệ căn cứ, tạo ra khiên chắn 40 HP bảo vệ căn cứ khỏi sát thương.",
            "cost": 30,
            "is_starter": False,
            "is_unlockable": True,
            "is_active": True,
            "base_stats": {
                "hp": 100,
                "damage": 0,
                "range": 0,
                "movement": 0,
                "shield": 40,
                "cooldown_rounds": 2,
                "strategic_role": "Gia cố khiên phòng ngự khẩn cấp khi căn cứ bị uy hiếp.",
            },
        },
    ]

    for item in STANDARD_UNITS:
        UnitType.objects.update_or_create(
            code=item["code"],
            defaults={
                "name": item["name"],
                "category": item["category"],
                "description": item["description"],
                "cost": item["cost"],
                "is_starter": item["is_starter"],
                "is_unlockable": item["is_unlockable"],
                "is_active": item.get("is_active", True),
                "base_stats": item["base_stats"],
            },
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("units", "0002_gameentity_gameaction"),
    ]

    operations = [
        migrations.RunPython(seed_units, reverse_code=noop),
    ]
