from django import forms
from .models import InscricaoAudicao

class InscricaoAudicaoForm(forms.ModelForm):
    class Meta:
        model = InscricaoAudicao
        fields = ['nome_completo', 'whatsapp', 'idade', 'personagens']
        widgets = {
            'nome_completo': forms.TextInput(attrs={'placeholder': 'Digite seu nome completo', 'style': 'width: 100%; padding: 0.75rem; border: 1px solid #ddd; border-radius: 5px; font-size: 1rem;'}),
            'whatsapp': forms.TextInput(attrs={'placeholder': '(11) 99999-9999', 'style': 'width: 100%; padding: 0.75rem; border: 1px solid #ddd; border-radius: 5px; font-size: 1rem;'}),
            'idade': forms.NumberInput(attrs={'placeholder': 'Sua idade', 'style': 'width: 100%; padding: 0.75rem; border: 1px solid #ddd; border-radius: 5px; font-size: 1rem;', 'id': 'id_idade'}),
            'personagens': forms.SelectMultiple(attrs={'style': 'width: 100%; padding: 0.75rem; border: 1px solid #ddd; border-radius: 5px; font-size: 1rem;', 'id': 'id_personagens'}),
        }
    
    def save(self, commit=True):
        # Pega os valores selecionados (vem como lista)
        valores = self.cleaned_data.get('personagens')
        
        # Dicionário para converter códigos em nomes legíveis
        personagens_dict = {
            'thessalia': 'Thessália',
            'zyara': 'Zyara',
            'zyar': 'Zyar',
            'astela_nur': 'Astela Nur',
            'kai_ignus': 'Kai Ignus',
            'eldrick_felicius': 'Eldrick Felicius',
            'florine': 'Florine',
            'odessa': 'Odessa',
            'aurelia': 'Aurélia',
            'cora_del_amour': 'Cora del Amour',
            '3_marias': '3 Marias',
        }
        
        # Converte os valores para nomes legíveis
        if isinstance(valores, list):
            nomes = [personagens_dict.get(v, v) for v in valores]
            personagens_texto = ', '.join(nomes)
        else:
            personagens_texto = valores
        
        # Cria a instância
        instance = self.instance
        instance.nome_completo = self.cleaned_data.get('nome_completo')
        instance.whatsapp = self.cleaned_data.get('whatsapp')
        instance.idade = self.cleaned_data.get('idade')
        instance.personagens = personagens_texto
        
        if commit:
            instance.save()
        return instance