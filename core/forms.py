from django import forms


class ImportPeopleForm(forms.Form):
    data_file = forms.FileField(
        label="Fichier CSV ou Excel",
        help_text="Colonnes attendues : matricule, nom complet, filiere, encadrant.",
        widget=forms.ClearableFileInput(attrs={
            "class": "form-control",
            "accept": ".csv,.xlsx",
        })
    )

    def clean_data_file(self):
        data_file = self.cleaned_data["data_file"]
        extension = data_file.name.rsplit(".", 1)[-1].lower()
        if extension not in {"csv", "xlsx"}:
            raise forms.ValidationError("Le fichier doit etre au format CSV ou XLSX.")
        return data_file


class ImportStudentReferencesForm(forms.Form):
    data_file = forms.FileField(
        label="Liste officielle CSV ou Excel",
        help_text=(
            "Colonnes attendues : matricule, nom complet, filiere, encadrant. "
            "Les professeurs manquants seront crees automatiquement."
        ),
        widget=forms.ClearableFileInput(attrs={
            "class": "form-control",
            "accept": ".csv,.xlsx",
        })
    )

    def clean_data_file(self):
        data_file = self.cleaned_data["data_file"]
        extension = data_file.name.rsplit(".", 1)[-1].lower()
        if extension not in {"csv", "xlsx"}:
            raise forms.ValidationError("Le fichier doit etre au format CSV ou XLSX.")
        return data_file
