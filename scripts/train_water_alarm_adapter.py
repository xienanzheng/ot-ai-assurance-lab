"""MLX LoRA entrypoint with exactly the deployment chat template and prompt mask."""


def process_chat(self,row):
    messages=row[self.chat_key]
    full=self.tokenizer.apply_chat_template(messages,return_dict=False,enable_thinking=False)
    prompt=self.tokenizer.apply_chat_template(messages[:-1],return_dict=False,
                                              enable_thinking=False,add_generation_prompt=True)
    if full[:len(prompt)]!=prompt:raise ValueError('Training prefix differs from deployment prompt')
    if len(full)>4096:raise ValueError('Training context too large; truncation forbidden')
    if not self.mask_prompt:raise ValueError('Water candidate requires prompt-masked loss')
    return full,len(prompt)


if __name__=='__main__':
    from mlx_lm.tuner.datasets import ChatDataset
    from mlx_lm.lora import main
    ChatDataset.process=process_chat
    main()
