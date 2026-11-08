from django.db import models

# Create your models here.

class Ingredient(models.Model):
    name = models.CharField(max_length=100, unique=True)
    grams_per_cup = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)

class Recipe(models.Model):
    title = models.CharField(max_length=200)
    yield_quantity = models.DecimalField(max_digits=8, decimal_places=2)
    yield_unit = models.CharField(max_length=30) # 'loaves", "dozen"
    instructions = models.TextField()

class RecipeIngredient(models.Model):
    recipe = models.ForeignKey(Recipe, related_name="items", on_delete=models.CASCADE)
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10, decimal_places=3)
    unit = models.CharField(max_length=10) # g, kg, oz, cup, tbsp... etc

    