from flask import Flask, render_template

app = Flask(__name__)

# VERİTABANINI DIŞARI ALDIK VE ID EKLEDIK
film_veritabanı = [
    {
        "id": 1825,
        "isim": "The Dark Knight",
        "puan": "9.0",
        "resim": "https://image.tmdb.org/t/p/w500/qJ2tW6WMUDux911r6m7haRef0WH.jpg",
        "konu": "Batman, Joker'in yarattığı kaosa karşı Gotham'ı savunmaya çalışır."
    },
    {
        "id": 2225,
        "isim": "Inception",
        "puan": "8.8",
        "resim": "https://i.ebayimg.com/images/g/FfsAAOSwrjNgr3rc/s-l1200.jpg",
        "konu": "Bir hırsız, insanların rüyalarına girip sırlarını çalar."
    },
    {
        "id": 1425,
        "isim": "Interstellar",
        "puan": "8.6",
        "resim": "https://image.tmdb.org/t/p/w500/gEU2QniE6E77NI6lCU6MxlNBvIx.jpg",
        "konu": "İnsanlığın kurtuluşu için solucan deliğinden geçen astronotlar."
    },
    {
        "id": 1725,
        "isim": "Matrix",
        "puan": "8.7",
        "resim": "https://image.tmdb.org/t/p/w500/f89U3ADr1oiB1s9GkdPOEpXUk5H.jpg",
        "konu": "Neo, yaşadığı dünyanın bir simülasyon olduğunu keşfeder."
    },
    {
        "id": 1925,
        "isim" : "V for Vendetta",
        "puan" : "8.1",
        "resim": "https://tr.web.img4.acsta.net/pictures/bzp/01/58911.jpg",
        "konu" : "2020'li yılların İngiltere'sinde geçen filmde halkın uyanış öyküsü.",
    },
    {
        "id": 6225,
        "isim": "Avengers Endgame",
        "puan": "8.4",
        "resim": "https://preview.redd.it/1sdabp4nt2m21.jpg?width=640&crop=smart&auto=webp&s=1bc7ce8cc7482749dfc971224b6a470b09a4c640",
        "konu": "Thanos Sonsuzluk Savaşını kazanmıştır ve geride kalanlar yüzleşmelidir."
    },
    {
        "id": 7325,
        "isim": "Forrest Gump",
        "puan": "8.5",
        "resim": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQp1gYXIb59BoLic17holJF-TWKBI5DINC6_Q&s",
        "konu": "Forrest Gump, düşük I.Q. sahibi genç bir adamdır. Jenny ile tanıştığında ona aşık olur.",
        
    }
]

@app.route("/")
def anasayfa():
    return render_template("index.html", filmler=film_veritabanı)

# DETAY SAYFASI ROTASI
@app.route("/film/<int:id>")
def film_detay(id):
    secilen_film = None
    for film in film_veritabanı:
        if film["id"] == id:
            secilen_film = film
            break
            
    if secilen_film:
        return render_template("detay.html", film=secilen_film)
    else:
        return "Film bulunamadı", 404

# DÜZELTİLEN KISIM: ARTIK SOLA YASLI (GLOBAL)
@app.route("/profil")
def profil():
    kullanici_bilgisi = {
        "ad": "İbrahim Çelik",
        "kullanici_adi": "@ibrahimcelik0",
        "resim": "https://images.pexels.com/photos/771742/pexels-photo-771742.jpeg?auto=compress&cs=tinysrgb&dpr=1&w=500",
        "bio": "Merhaba ben İbrahim! Yazılım ve sinema tutkunuyum. Favori filmim Interstellar.",
        "uyelik_tarihi": "Aralık 2025"
    }
    return render_template("profil.html", kullanici=kullanici_bilgisi)
@app.route('/detay')
def detay():
    return render_template('detay.html') 
@app.route("/yorum_yap/<string:film_ismi>")
def yorum_yap(film_ismi):
    return render_template('yorum.html', film_adi=film_ismi)
    
if __name__ == "__main__":
    app.run(debug=True)