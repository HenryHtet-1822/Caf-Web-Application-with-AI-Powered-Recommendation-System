# %%
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import requests

# %%
menu_df = pd.read_csv("menu_items.csv")
# %%
category_map = {
    1: "Breakfast",
    2: "Lunch Specials",
    3: "Dinner Dishes",
    4: "Desserts",
    5: "Hot Drinks",
    6: "Cold Drinks",
    7: "Salads and Sides",
    8: "Kid's Menu"
}
# %%
menu_df["category_name"] = menu_df["category_id"].map(category_map)

# %%
menu_df["features"] = (
        menu_df["recipe_name"].fillna('') + " " +
        menu_df["cuisine_path"].fillna('') + " " +
        menu_df["cleaned_ingredients"].fillna('') + " " +
        menu_df["ingredients"].fillna('')
)

# %%
tfidf = TfidfVectorizer(stop_words="english")
tfidf_matrix = tfidf.fit_transform(menu_df["recipe_name"] + " " + menu_df["ingredients"])
cosine_sim = cosine_similarity(tfidf_matrix, tfidf_matrix)

# %%
indices = pd.Series(menu_df.index, index=menu_df["recipe_name"]).drop_duplicates()


# %%
def recommend_menu(item_name, num_recommendations=5):
    if item_name not in menu_df["recipe_name"].values:
        return f"{item_name} not found in dataset."

    # Get index of the item
    idx = menu_df.index[menu_df["recipe_name"] == item_name][0]

    # Get similarity scores for this item
    sim_scores = list(enumerate(cosine_sim[idx]))

    # Sort by similarity (highest first), skip the item itself
    sim_scores = sorted(sim_scores, key=lambda x: x[1], reverse=True)[1:num_recommendations + 1]

    # Get recommended item indices
    item_indices = [i[0] for i in sim_scores]

    return menu_df.iloc[item_indices][["recipe_name", "ingredients", "category_id", "price"]]



# %%
menu_df['category_name'] = menu_df['category_id'].map(category_map)
# %%
weather_to_category = {
    "Clear": ["Cold Drinks", "Salads and Sides", "Breakfast", "Desserts"],
    "Hot": ["Cold Drinks", "Desserts", "Salads and Sides"],
    "Rain": ["Hot Drinks", "Dinner Dishes"],
    "Drizzle": ["Hot Drinks", "Lunch Specials"],
    "Clouds": ["Hot Drinks", "Lunch Specials", "Dinner Dishes"],
    "Thunderstorm": ["Hot Drinks", "Dinner Dishes"],
    "Mist": ["Hot Drinks", "Breakfast"],
    "Haze": ["Cold Drinks", "Salads and Sides", "Lunch Specials"],
    "Fog": ["Hot Drinks", "Breakfast"],
    "Smoke": ["Hot Drinks", "Lunch Specials"],
    "Dust": ["Cold Drinks", "Salads and Sides"]
}


# %%
def get_myanmar_weather_by_latlon(lat, lon, api_key):
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=metric"
    response = requests.get(url).json()
    weather = response["weather"][0]["main"]
    temp = response["main"]["temp"]
    return weather, temp


# %%
def recommend_menu_with_weather(item_name, lat=16.8409, lon=96.1735, api_key="f7c3d772751b67eb57a49e49dda6e3ed",
                                num_recommendations=8):

    item_based = recommend_menu(item_name, num_recommendations)

    weather, temp = get_myanmar_weather_by_latlon(lat, lon, api_key)
    recommended_categories = weather_to_category.get(weather, [])

    weather_based = menu_df[menu_df['category_name'].isin(recommended_categories)].head(num_recommendations)
    weather_based = weather_based[[
        "recipe_name", "ingredients", "category_id", "category_name", "price", "img_src"
    ]]

    return {
        "clicked_item_recommendation": item_based,
        "weather_based_recommendation": weather_based,
        "weather": weather,
        "temperature": temp
    }

# %%
if __name__ == "__main__":
    # Ask the user for the menu item they clicked
    user_item = input("Enter the menu item you want recommendations for: ")

    # Call the weather-based recommendation
    result = recommend_menu_with_weather(user_item, api_key="f7c3d772751b67eb57a49e49dda6e3ed")

    # Display results
    print("\nWeather:", result["weather"], "-", result["temperature"])
    print("\nItem-based recommendation:\n", result["clicked_item_recommendation"])
    print("\nWeather-based recommendation:\n", result["weather_based_recommendation"])

# %%
print(menu_df.columns)
