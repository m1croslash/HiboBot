from flask import Flask
from threading import Thread
import discord
from discord import app_commands
import os
from datetime import datetime
from dotenv import load_dotenv

app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

keep_alive()

load_dotenv()

class StaffBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.warnings = {} 

    async def on_ready(self):
        print(f'✅ {self.user} ready to work!')
        try:
            synced = await self.tree.sync()
            print(f'🔧 Commands synced: {len(synced)}')
        except Exception as e:
            print(f'❌ Error syncing commands: {e}')

    async def send_to_employee_dm(self, employee: discord.Member, embed: discord.Embed):
        try:
            await employee.send(embed=embed)
        except discord.Forbidden:
            print(f"Не удалось отправить сообщение {employee.name} - закрытые ЛС")

    async def auto_dismiss_employee(self, interaction: discord.Interaction, employee: discord.Member):
        start_date = employee.joined_at.strftime("%d.%m.%Y")
        embed = discord.Embed(
            title="🚪 Автоматическое увольнение работника", 
            color=0xff0000,
            description="*Причина: достигнуто максимальное количество выговоров*"
        )
        embed.add_field(name="Работник", value=employee.mention, inline=True)
        embed.add_field(name="Период работы", value=f"{start_date} - {datetime.now().strftime('%d.%m.%Y')}", inline=False)
        embed.add_field(name="Количество выговоров", value="3/3", inline=True)
        embed.set_footer(text="Автоматическое увольнение")
        
        await interaction.followup.send(embed=embed)
        await self.send_to_employee_dm(employee, embed)
        
        roles_to_remove = [1434494581700825229]
        for role_id in roles_to_remove:
            role = employee.guild.get_role(role_id)
            if role and role in employee.roles:
                try:
                    await employee.remove_roles(role)
                    print(f"Удалена роль {role.name} у {employee.name}")
                except Exception as e:
                    print(f"Ошибка при удалении роли {role_id}: {e}")

    async def setup_hook(self):
        async def is_guild(interaction: discord.Interaction) -> bool:
            if interaction.guild is None:
                await interaction.response.send_message(
                    "❌ Команды можно использовать только на сервере!",
                    ephemeral=True
                )
                return False
            return True

        @self.tree.command(name="выговор", description="Выдает выговор работнику")
        @app_commands.describe(employee="Выберите работника", reason="Причина для выговора")
        async def warn(interaction: discord.Interaction, employee: discord.Member, reason: str):
            if not await is_guild(interaction):
                return
                
            allowed_roles_ids = [1434201626062880838]
            user_roles = [role.id for role in interaction.user.roles]
            
            if not any(role in allowed_roles_ids for role in user_roles) and interaction.user.id != employee.id:
                await interaction.response.send_message("❌ Недостаточно прав", ephemeral=True)
                return
            
            if employee.id not in self.warnings:
                self.warnings[employee.id] = 0
            self.warnings[employee.id] += 1
            
            MAX_WARNINGS = 3
            current_warnings = self.warnings[employee.id]
            
            if current_warnings >= MAX_WARNINGS:
                embed = discord.Embed(title="⚠️ Выговор работника", color=0xff0000)
                embed.add_field(name="Работник", value=employee.mention, inline=True)
                embed.add_field(name="Причина", value=reason, inline=False)
                embed.add_field(name="Дата", value=datetime.now().strftime("%d.%m.%Y"), inline=True)
                embed.add_field(name="Выговоры", value=f"{current_warnings}/{MAX_WARNINGS}", inline=True)
                
                await interaction.response.send_message(embed=embed)
                await self.send_to_employee_dm(employee, embed)
                
                del self.warnings[employee.id]
                await self.auto_dismiss_employee(interaction, employee)
                return
            
            embed = discord.Embed(title="⚠️ Выговор работника", color=0xff0000)
            embed.add_field(name="Работник", value=employee.mention, inline=True)
            embed.add_field(name="Причина", value=reason, inline=False)
            embed.add_field(name="Дата", value=datetime.now().strftime("%d.%m.%Y"), inline=True)
            embed.add_field(name="Выговоры", value=f"{current_warnings}/{MAX_WARNINGS}", inline=True)
            
            await interaction.response.send_message(embed=embed)
            await self.send_to_employee_dm(employee, embed)

        @self.tree.command(name="снять_выговор", description="Снимает выговор у работника")
        @app_commands.describe(employee="Выберите работника", amount="Количество выговоров для снятия", reason="Причина снятия")
        async def remove_warn(interaction: discord.Interaction, employee: discord.Member, amount: int = 1, reason: str = "Не указана"):
            if not await is_guild(interaction):
                return
                
            allowed_roles_ids = [1434201626062880838]
            user_roles = [role.id for role in interaction.user.roles]
            
            if not any(role in allowed_roles_ids for role in user_roles):
                await interaction.response.send_message("❌ Недостаточно прав", ephemeral=True)
                return
            
            if employee.id not in self.warnings or self.warnings[employee.id] <= 0:
                await interaction.response.send_message("❌ У этого работника нет выговоров", ephemeral=True)
                return
            
            self.warnings[employee.id] = max(0, self.warnings[employee.id] - amount)
            
            if self.warnings[employee.id] == 0:
                del self.warnings[employee.id]
                warnings_text = "0/3"
            else:
                warnings_text = f"{self.warnings[employee.id]}/3"
            
            embed = discord.Embed(title="✅ Снятие выговора", color=0x00ff00)
            embed.add_field(name="Работник", value=employee.mention, inline=True)
            embed.add_field(name="Снято выговоров", value=str(amount), inline=True)
            embed.add_field(name="Текущее количество", value=warnings_text, inline=True)
            embed.add_field(name="Причина снятия", value=reason, inline=False)
            embed.add_field(name="Дата", value=datetime.now().strftime("%d.%m.%Y"), inline=True)
            
            await interaction.response.send_message(embed=embed)
            await self.send_to_employee_dm(employee, embed)

        @self.tree.command(name="зарплата", description="Выплата")  
        @app_commands.describe(employee="Выберите работника", amount="Сумма выплаты", date="Дата выдачи")
        async def salary(interaction: discord.Interaction, employee: discord.Member, amount: str, date: str = None):
            if not await is_guild(interaction):
                return
                
            allowed_roles_ids = [1434201626062880838]
            user_roles = [role.id for role in interaction.user.roles]
            
            if not any(role in allowed_roles_ids for role in user_roles):
                await interaction.response.send_message("❌ Недостаточно прав", ephemeral=True)
                return
            
            payment_date = date or datetime.now().strftime("%d.%m.%Y")
            embed = discord.Embed(title="💰 Выплата", color=0x00ff00)
            embed.add_field(name="Работник", value=employee.mention, inline=True)
            embed.add_field(name="Дата выдачи", value=payment_date, inline=True)
            embed.add_field(name="Сумма", value=f"{amount} робуксов", inline=True)
            embed.set_footer(text=f"Выдал: {interaction.user.display_name}")
            
            await interaction.response.send_message(embed=embed)
            await self.send_to_employee_dm(employee, embed)

        @self.tree.command(name="увольнение", description="Увольнение работника")
        @app_commands.describe(employee="Выберите работника", reason="Причина увольнения")
        async def dismiss(interaction: discord.Interaction, employee: discord.Member, reason: str):
            if not await is_guild(interaction):
                return
                
            allowed_roles_ids = [1434201626062880838]
            user_roles = [role.id for role in interaction.user.roles]
            
            if not any(role in allowed_roles_ids for role in user_roles):
                await interaction.response.send_message("❌ Недостаточно прав", ephemeral=True)
                return
            
            if employee.id in self.warnings:
                del self.warnings[employee.id]
            
            start_date = employee.joined_at.strftime("%d.%m.%Y")
            embed = discord.Embed(title="🚪 Увольнение работника", color=0xff6b00)
            embed.add_field(name="Работник", value=employee.mention, inline=True)
            embed.add_field(name="Период работы", value=f"{start_date} - {datetime.now().strftime('%d.%m.%Y')}", inline=False)
            embed.add_field(name="Причина", value=reason, inline=False)
            embed.set_footer(text=f"Уволил: {interaction.user.display_name}")
            
            await interaction.response.send_message(embed=embed)
            await self.send_to_employee_dm(employee, embed)
            
            roles_to_remove = [1434494581700825229]
            for role_id in roles_to_remove:
                role = employee.guild.get_role(role_id)
                if role and role in employee.roles:
                    try:
                        await employee.remove_roles(role)
                        print(f"Удалена роль {role.name} у {employee.name}")
                    except Exception as e:
                        print(f"Ошибка при удалении роли {role_id}: {e}")

        @self.tree.command(name="отпуск", description="Отпуск работника")
        @app_commands.describe(employee="Выберите работника", reason="Причина", duration="Срок отпуска")
        async def vacation(interaction: discord.Interaction, employee: discord.Member, reason: str, duration: str):
            if not await is_guild(interaction):
                return
                
            allowed_roles_ids = [1434201626062880838]
            user_roles = [role.id for role in interaction.user.roles]

            if not any(role in allowed_roles_ids for role in user_roles):
                await interaction.response.send_message("❌ Недостаточно прав", ephemeral=True)
                return

            embed = discord.Embed(title="🏖️ Отпуск работника", color=0x00ffff)
            embed.add_field(name="Работник", value=employee.mention, inline=True)
            embed.add_field(name="Причина", value=reason, inline=False)
            embed.add_field(name="Срок", value=duration, inline=True)
            embed.add_field(name="Дата оформления", value=datetime.now().strftime("%d.%m.%Y"), inline=True)
            embed.set_footer(text=f"Оформил: {interaction.user.display_name}")
            
            await interaction.response.send_message(embed=embed)
            await self.send_to_employee_dm(employee, embed)

        @self.tree.command(name="тест", description="Проверка бота")
        async def test(interaction: discord.Interaction):
            if not await is_guild(interaction):
                return
            await interaction.response.send_message("✅ Бот работает")

bot = StaffBot()
bot.run(os.getenv('TOKEN'))
