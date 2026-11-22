"""Ortak kullanılan veri yapıları, yardımcı fonksiyonlar ve ölçeklenebilir arama yardımcıları."""

import math
import unicodedata
from typing import Any, Dict, List, Optional


# 5000+ Film & Dizi platformu için evrensel sinema/dizi tür kataloğu
EVRENSEL_TURLER: List[str] = [
    "Aksiyon",
    "Macera",
    "Animasyon",
    "Bilim Kurgu",
    "Biyografi",
    "Dram",
    "Fantastik",
    "Gerilim",
    "Gizem",
    "Komedi",
    "Korku",
    "Suç",
    "Romantik",
    "Savaş",
    "Tarih",
    "Belgesel",
    "Aile",
    "Müzikal",
]

ICERIK_TIPLERI: List[str] = ["Film", "Dizi"]


# Başlangıç film veri kaynağı (Mock Veritabanı - Mevcut 7 film korunmuştur)
FILM_VERITABANI: List[Dict[str, Any]] = [
    {
        "id": 1825,
        "isim": "The Dark Knight",
        "tip": "Film",
        "puan": "9.0",
        "yil": 2008,
        "tur": "Aksiyon, Suç, Dram",
        "yonetmen": "Christopher Nolan",
        "oyuncular": "Christian Bale, Heath Ledger, Gary Oldman",
        "resim": "https://image.tmdb.org/t/p/w500/qJ2tW6WMUDux911r6m7haRef0WH.jpg",
        "konu": "Batman, Joker'in yarattığı kaosa karşı Gotham'ı savunmaya çalışır."
    },
    {
        "id": 2225,
        "isim": "Inception",
        "tip": "Film",
        "puan": "8.8",
        "yil": 2010,
        "tur": "Bilim Kurgu, Aksiyon, Macera",
        "yonetmen": "Christopher Nolan",
        "oyuncular": "Leonardo DiCaprio, Joseph Gordon-Levitt, Elliot Page",
        "resim": "https://i.ebayimg.com/images/g/FfsAAOSwrjNgr3rc/s-l1200.jpg",
        "konu": "Bir hırsız, insanların rüyalarına girip sırlarını çalar."
    },
    {
        "id": 1425,
        "isim": "Interstellar",
        "tip": "Film",
        "puan": "8.6",
        "yil": 2014,
        "tur": "Bilim Kurgu, Dram, Macera",
        "yonetmen": "Christopher Nolan",
        "oyuncular": "Matthew McConaughey, Anne Hathaway, Jessica Chastain",
        "resim": "https://image.tmdb.org/t/p/w500/gEU2QniE6E77NI6lCU6MxlNBvIx.jpg",
        "konu": "İnsanlığın kurtuluşu için solucan deliğinden geçen astronotlar."
    },
    {
        "id": 1725,
        "isim": "Matrix",
        "tip": "Film",
        "puan": "8.7",
        "yil": 1999,
        "tur": "Bilim Kurgu, Aksiyon",
        "yonetmen": "Lana & Lilly Wachowski",
        "oyuncular": "Keanu Reeves, Laurence Fishburne, Carrie-Anne Moss",
        "resim": "https://image.tmdb.org/t/p/w500/f89U3ADr1oiB1s9GkdPOEpXUk5H.jpg",
        "konu": "Neo, yaşadığı dünyanın bir simülasyon olduğunu keşfeder."
    },
    {
        "id": 1925,
        "isim": "V for Vendetta",
        "tip": "Film",
        "puan": "8.1",
        "yil": 2005,
        "tur": "Aksiyon, Dram, Gerilim",
        "yonetmen": "James McTeigue",
        "oyuncular": "Hugo Weaving, Natalie Portman, Stephen Rea",
        "resim": "https://tr.web.img4.acsta.net/pictures/bzp/01/58911.jpg",
        "konu": "2020'li yılların İngiltere'sinde geçen filmde halkın uyanış öyküsü."
    },
    {
        "id": 6225,
        "isim": "Avengers Endgame",
        "tip": "Film",
        "puan": "8.4",
        "yil": 2019,
        "tur": "Aksiyon, Bilim Kurgu, Macera",
        "yonetmen": "Anthony & Joe Russo",
        "oyuncular": "Robert Downey Jr., Chris Evans, Scarlett Johansson",
        "resim": "https://preview.redd.it/1sdabp4nt2m21.jpg?width=640&crop=smart&auto=webp&s=1bc7ce8cc7482749dfc971224b6a470b09a4c640",
        "konu": "Thanos Sonsuzluk Savaşını kazanmıştır ve geride kalanlar yüzleşmelidir."
    },
    {
        "id": 7325,
        "isim": "Forrest Gump",
        "tip": "Film",
        "puan": "8.5",
        "yil": 1994,
        "tur": "Dram, Romantik",
        "yonetmen": "Robert Zemeckis",
        "oyuncular": "Tom Hanks, Robin Wright, Gary Sinise",
        "resim": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQp1gYXIb59BoLic17holJF-TWKBI5DINC6_Q&s",
        "konu": "Forrest Gump, düşük I.Q. sahibi genç bir adamdır. Jenny ile tanıştığında ona aşık olur."
    }
]


def find_by_field(items: List[Dict[str, Any]], field: str, value: Any) -> Optional[Dict[str, Any]]:
    """Verilen sözlük listesinde belirli bir alan ve değere göre ilk eşleşen kaydı döndürür."""
    for item in items:
        if item.get(field) == value:
            return item
    return None


def normalize_search_text(text: str) -> str:
    """
    Büyük/küçük harf ve Türkçe İ/I/ı/i farkını tamamen ortadan kaldırır.
    Örn: 'Interstellar', 'interstellar', 'İNTERSTELLAR' -> 'interstellar'
    """
    if not text:
        return ""
    tr_map = str.maketrans({
        "İ": "i", "I": "i", "ı": "i", "i": "i",
        "Ç": "c", "ç": "c",
        "Ğ": "g", "ğ": "g",
        "Ö": "o", "ö": "o",
        "Ş": "s", "ş": "s",
        "Ü": "u", "ü": "u",
    })
    cleaned = text.translate(tr_map).lower()
    cleaned = unicodedata.normalize("NFD", cleaned)
    cleaned = "".join(ch for ch in cleaned if unicodedata.category(ch) != "Mn")
    return cleaned.strip()


def levenshtein_distance(s1: str, s2: str) -> int:
    """İki metin arasındaki düzenleme (yazım hatası) mesafesini hesaplar."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def fuzzy_text_match(raw_target: str, raw_query: str) -> bool:
    """
    Büyük/küçük harf duyarsız ve yazım hatası toleranslı (Örn: Intersteller == intersteller -> Interstellar)
    metin eşleşmesi yapar.
    """
    target = normalize_search_text(raw_target)
    query = normalize_search_text(raw_query)
    if not query:
        return True
    if not target:
        return False

    if query in target:
        return True

    if len(query) >= 4:
        max_dist = 2 if len(query) >= 8 else 1
        if levenshtein_distance(target[:len(query)], query) <= max_dist:
            return True
        for word in target.split():
            if abs(len(word) - len(query)) <= max_dist and levenshtein_distance(word, query) <= max_dist:
                return True
            word_slice = word[:len(query)]
            if len(word_slice) >= 4 and levenshtein_distance(word_slice, query) <= max_dist:
                return True

    return False
